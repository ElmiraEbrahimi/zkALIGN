package circuit

// This file is an application-level audit, not a batch or recursive circuit.
// The auditor must approve and pin the manifest BEFORE accepting proof files.
import (
	"bufio"
	"bytes"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"github.com/ElmiraEbrahimi/zkALIGN/hashing"
	"io"
	"math/big"
	"os"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
)

// v4 requires the roster to reconstruct the entire snapshot, not a subset.
// The private-cost circuit and its keys are unchanged from v3. Old manifests
// and bundles must be regenerated and approved under the full-snapshot policy.
const AuditVersion = "zkalign-single-trace-audit-v4-mimc-full-snapshot"

// AuditCase is an agreed population member. Indices and commitments are public;
// patient identifiers, activities, salts and alignments are not included.
type AuditCase struct {
	Index      uint32 `json:"index"`
	Commitment string `json:"commitment"`
}

type AuditManifest struct {
	Version             string      `json:"version"`
	Root                string      `json:"root"`
	VerificationKeyMiMC string      `json:"verification_key_mimc"`
	Threshold           int         `json:"threshold"`
	TargetPercent       int         `json:"target_percent"`
	Cases               []AuditCase `json:"cases"`
}

// A bundle contains only a single proof and its public commitment. Root,
// threshold and verification key come from the pinned manifest, not the bundle.
type AuditProofBundle struct {
	ManifestMiMC string `json:"manifest_mimc"`
	Commitment   string `json:"commitment"`
	Proof        []byte `json:"proof"`
}

type AuditReceipt struct {
	File   string `json:"file"`
	Status string `json:"status"`
	Reason string `json:"reason,omitempty"`
}

type AuditReport struct {
	ManifestMiMC       string         `json:"manifest_mimc"`
	Population         int            `json:"population"`
	Certified          int            `json:"certified"`
	Uncertified        int            `json:"uncertified"`
	Required           int            `json:"required"`
	TargetPercent      int            `json:"target_percent"`
	Threshold          int            `json:"threshold"`
	TargetMet          bool           `json:"target_met"`
	CertifiedIndices   []uint32       `json:"certified_indices"`
	UncertifiedIndices []uint32       `json:"uncertified_indices"`
	Receipts           []AuditReceipt `json:"receipts"`
}

func canonicalField(s string) (*big.Int, error) {
	n, ok := new(big.Int).SetString(s, 10)
	if !ok || n.Sign() < 0 || n.Cmp(ecc.BN254.ScalarField()) >= 0 || n.String() != s {
		return nil, fmt.Errorf("noncanonical BN254 field value")
	}
	return n, nil
}

func (m AuditManifest) Validate() error {
	if m.Version != AuditVersion || len(m.Cases) == 0 {
		return fmt.Errorf("unsupported or empty audit manifest")
	}
	if m.Threshold < 0 || m.TargetPercent < 1 || m.TargetPercent > 100 {
		return fmt.Errorf("threshold must be nonnegative and target must be 1..100")
	}
	if _, err := canonicalField(m.Root); err != nil {
		return fmt.Errorf("root: %w", err)
	}
	keyHash, err := hex.DecodeString(m.VerificationKeyMiMC)
	if err != nil || len(keyHash) != 32 || hex.EncodeToString(keyHash) != m.VerificationKeyMiMC || new(big.Int).SetBytes(keyHash).Cmp(ecc.BN254.ScalarField()) >= 0 {
		return fmt.Errorf("invalid verification-key fingerprint")
	}
	indices, commitments := map[uint32]bool{}, map[string]bool{}
	leaves := make(map[uint32]*big.Int, len(m.Cases))
	for _, entry := range m.Cases {
		commitment, err := canonicalField(entry.Commitment)
		if err != nil {
			return fmt.Errorf("commitment: %w", err)
		}
		// Zero at index 0 hashes to the default empty leaf. Do not allow an
		// empty tree position to be counted as a committed case.
		if commitment.Sign() == 0 {
			return fmt.Errorf("zero commitment is reserved for empty leaves")
		}
		if uint64(entry.Index) >= uint64(len(m.Cases)) {
			return fmt.Errorf("population indices must be exactly 0..N-1")
		}
		if indices[entry.Index] || commitments[entry.Commitment] {
			return fmt.Errorf("duplicate population index or commitment")
		}
		indices[entry.Index], commitments[entry.Commitment] = true, true
		leaves[entry.Index] = circuitMerkleLeaf(entry.Index, commitment)
	}
	// N unique indices in [0,N) give the complete contiguous index set.
	// Reuse the witness tree builder, including all 32 default subtrees.
	if buildCircuitMerkleProof(leaves, 0).Root.String() != m.Root {
		return fmt.Errorf("population does not reconstruct the approved snapshot root")
	}
	return nil
}

// RequiredCertified computes ceil(N * percent / 100) without floating point
// or a potentially overflowing multiplication by N.
func RequiredCertified(population, percent int) int {
	return (population/100)*percent + ((population%100)*percent+99)/100
}

// LoadAuditContext requires a digest retained through an independent trusted
// channel. Reading a digest from the prover's own folder is only a demo.
func LoadAuditContext(manifestBytes []byte, approvedDigest string, vkBytes []byte) (AuditManifest, groth16.VerifyingKey, error) {
	var manifest AuditManifest
	if approvedDigest == "" || hashing.Manifest(manifestBytes) != approvedDigest {
		return manifest, nil, fmt.Errorf("manifest does not match the auditor's approved digest")
	}
	if err := json.Unmarshal(manifestBytes, &manifest); err != nil {
		return manifest, nil, err
	}
	if err := manifest.Validate(); err != nil {
		return manifest, nil, err
	}
	if hashing.VerificationKey(vkBytes) != manifest.VerificationKeyMiMC {
		return manifest, nil, fmt.Errorf("verification key differs from approved key")
	}
	vk := groth16.NewVerifyingKey(ecc.BN254)
	reader := bytes.NewReader(vkBytes)
	if _, err := vk.ReadFrom(reader); err != nil {
		return manifest, nil, fmt.Errorf("decode verification key: %w", err)
	}
	if reader.Len() != 0 {
		return manifest, nil, fmt.Errorf("trailing verification-key data")
	}
	return manifest, vk, nil
}

type AuditVerifier struct {
	manifest AuditManifest
	digest   string
	vk       groth16.VerifyingKey
	expected map[string]bool
	accepted map[string]bool
	receipts []AuditReceipt
}

func NewAuditVerifier(manifestBytes []byte, approvedDigest string, vkBytes []byte) (*AuditVerifier, error) {
	m, vk, err := LoadAuditContext(manifestBytes, approvedDigest, vkBytes)
	if err != nil {
		return nil, err
	}
	v := &AuditVerifier{manifest: m, digest: approvedDigest, vk: vk, expected: map[string]bool{}, accepted: map[string]bool{}}
	for _, entry := range m.Cases {
		v.expected[entry.Commitment] = true
	}
	return v, nil
}

// Check records malformed, invalid, unexpected and duplicate submissions but
// never removes a case from the denominator. An invalid attempt cannot block
// a later valid proof for that case.
func (v *AuditVerifier) Check(name string, data []byte) {
	receipt := AuditReceipt{File: name, Status: "invalid"}
	var bundle AuditProofBundle
	// Reject legacy cost-bearing bundles and other unexpected public fields.
	// This also prevents accidental exact-cost disclosure in accepted packages.
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	err := decoder.Decode(&bundle)
	if err == nil {
		var extra any
		if trailing := decoder.Decode(&extra); trailing != io.EOF {
			err = fmt.Errorf("proof bundle must contain exactly one JSON object")
		}
	}
	if err == nil {
		err = v.verifyBundle(bundle)
	}
	if err != nil {
		receipt.Reason = err.Error()
	} else if v.accepted[bundle.Commitment] {
		receipt.Status = "duplicate"
		receipt.Reason = "valid proof for an already certified population member"
	} else {
		v.accepted[bundle.Commitment] = true
		receipt.Status = "accepted"
	}
	v.receipts = append(v.receipts, receipt)
}

func (v *AuditVerifier) verifyBundle(bundle AuditProofBundle) error {
	if bundle.ManifestMiMC != v.digest {
		return fmt.Errorf("proof belongs to a different audit manifest")
	}
	if !v.expected[bundle.Commitment] {
		return fmt.Errorf("commitment is not in the agreed population")
	}
	commitment, _ := canonicalField(bundle.Commitment)
	root, _ := canonicalField(v.manifest.Root)
	public, err := frontend.NewWitness(&SingleTracePetriNetCircuit{
		TraceCommitment: commitment, EventLogRoot: root,
		CostThreshold: v.manifest.Threshold,
	}, ecc.BN254.ScalarField(), frontend.PublicOnly())
	if err != nil {
		return err
	}
	proof := groth16.NewProof(ecc.BN254)
	reader := bytes.NewReader(bundle.Proof)
	if _, err := proof.ReadFrom(reader); err != nil {
		return fmt.Errorf("decode proof: %w", err)
	}
	if reader.Len() != 0 {
		return fmt.Errorf("trailing proof data")
	}
	return VerifyGroth16Proof(proof, v.vk, public)
}

func (v *AuditVerifier) Report() AuditReport {
	r := AuditReport{ManifestMiMC: v.digest, Population: len(v.manifest.Cases), Certified: len(v.accepted), TargetPercent: v.manifest.TargetPercent, Threshold: v.manifest.Threshold, Receipts: v.receipts}
	r.Required = RequiredCertified(r.Population, r.TargetPercent)
	r.Uncertified = r.Population - r.Certified
	r.TargetMet = r.Certified >= r.Required
	for _, entry := range v.manifest.Cases {
		if v.accepted[entry.Commitment] {
			r.CertifiedIndices = append(r.CertifiedIndices, entry.Index)
		} else {
			r.UncertifiedIndices = append(r.UncertifiedIndices, entry.Index)
		}
	}
	return r
}

// PrepareAuditPopulation includes every stored case. Subset rosters are not
// supported: the population must reconstruct the complete committed snapshot.
// Returned case IDs are private and used only by the prover CLI.
func PrepareAuditPopulation(recordsPath string) (string, []AuditCase, map[uint32]string, error) {
	f, err := os.Open(recordsPath)
	if err != nil {
		return "", nil, nil, err
	}
	defer f.Close()
	seenIDs, seenIndices := map[string]bool{}, map[uint32]bool{}
	entries := []AuditCase{}
	ids := map[uint32]string{}
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		var record privateTraceRecord
		if err := json.Unmarshal(scanner.Bytes(), &record); err != nil {
			return "", nil, nil, err
		}
		if record.HashScheme != hashing.Scheme {
			return "", nil, nil, fmt.Errorf("legacy records require explicit MiMC migration")
		}
		if record.CaseID == "" || seenIDs[record.CaseID] || seenIndices[record.Index] {
			return "", nil, nil, fmt.Errorf("empty or duplicate case ID or index in records")
		}
		seenIDs[record.CaseID], seenIndices[record.Index] = true, true
		if len(record.ActivityIDs) > MaxTraceEvents {
			return "", nil, nil, fmt.Errorf("record exceeds trace capacity")
		}
		var trace [MaxTraceEvents]int
		for j, activity := range record.ActivityIDs {
			if activity < 1 || activity > ActivityCount {
				return "", nil, nil, fmt.Errorf("invalid activity identifier")
			}
			trace[j] = activity
		}
		salt, ok := new(big.Int).SetString(record.Salt, 16)
		if !ok || salt.Sign() < 0 {
			return "", nil, nil, fmt.Errorf("invalid salt")
		}
		entries = append(entries, AuditCase{Index: record.Index, Commitment: ComputeTraceCommitment(len(record.ActivityIDs), trace, salt).String()})
		ids[record.Index] = record.CaseID
	}
	if err := scanner.Err(); err != nil {
		return "", nil, nil, err
	}
	if len(entries) == 0 {
		return "", nil, nil, fmt.Errorf("empty population")
	}
	for _, entry := range entries {
		if uint64(entry.Index) >= uint64(len(entries)) {
			return "", nil, nil, fmt.Errorf("record indices must be exactly 0..N-1")
		}
	}
	path, err := loadCircuitMerkleProof(recordsPath, entries[0].Index)
	if err != nil {
		return "", nil, nil, err
	}
	return path.Root.String(), entries, ids, nil
}
