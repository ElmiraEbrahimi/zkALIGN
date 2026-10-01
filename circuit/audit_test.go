package circuit

import (
	"bytes"
	"encoding/json"
	"github.com/ElmiraEbrahimi/zkALIGN/hashing"
	"math/big"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
)

func TestAuditPercentageBoundary(t *testing.T) {
	for _, test := range []struct{ n, percent, want int }{{100, 95, 95}, {101, 95, 96}, {3, 95, 3}, {20, 95, 19}, {1050, 95, 998}, {1, 1, 1}, {100, 100, 100}} {
		if got := RequiredCertified(test.n, test.percent); got != test.want {
			t.Fatalf("N=%d target=%d: got %d want %d", test.n, test.percent, got, test.want)
		}
	}
}

func TestAuditManifestValidation(t *testing.T) {
	base := AuditManifest{Version: AuditVersion, Root: "1", VerificationKeyMiMC: strings.Repeat("0", 63) + "1", Threshold: 1, TargetPercent: 95, Cases: []AuditCase{{Index: 0, Commitment: "2"}, {Index: 1, Commitment: "3"}}}
	if err := base.Validate(); err != nil {
		t.Fatal(err)
	}
	for name, mutate := range map[string]func(*AuditManifest){
		"duplicate commitment": func(m *AuditManifest) { m.Cases[1].Commitment = "2" },
		"duplicate index":      func(m *AuditManifest) { m.Cases[1].Index = 0 },
		"field alias":          func(m *AuditManifest) { m.Cases[1].Commitment = "03" },
		"field overflow":       func(m *AuditManifest) { m.Root = ecc.BN254.ScalarField().String() },
		"empty population":     func(m *AuditManifest) { m.Cases = nil },
		"negative threshold":   func(m *AuditManifest) { m.Threshold = -1 },
		"invalid target":       func(m *AuditManifest) { m.TargetPercent = 101 },
		"bad fingerprint":      func(m *AuditManifest) { m.VerificationKeyMiMC = "bad" },
		"legacy public cost":   func(m *AuditManifest) { m.Version = "zkalign-single-trace-audit-v2-mimc" },
	} {
		t.Run(name, func(t *testing.T) {
			m := base
			m.Cases = append([]AuditCase(nil), base.Cases...)
			mutate(&m)
			if m.Validate() == nil {
				t.Fatal("invalid manifest accepted")
			}
		})
	}
}

// Accounting-only boundary test. Acceptance itself is covered below with
// actual Groth16 proofs; production callers cannot populate this private map.
func TestAuditNinetyFiveOfOneHundred(t *testing.T) {
	v := &AuditVerifier{manifest: AuditManifest{TargetPercent: 95}, accepted: map[string]bool{}}
	for i := 0; i < 100; i++ {
		commitment := strconv.Itoa(i + 1)
		v.manifest.Cases = append(v.manifest.Cases, AuditCase{Index: uint32(i), Commitment: commitment})
		if i < 94 {
			v.accepted[commitment] = true
		}
	}
	if r := v.Report(); r.TargetMet || r.Uncertified != 6 {
		t.Fatalf("94/100 must not meet 95%%: %+v", r)
	}
	v.accepted["95"] = true
	if r := v.Report(); !r.TargetMet || r.Certified != 95 || r.Uncertified != 5 {
		t.Fatalf("95/100 must meet 95%%: %+v", r)
	}
}

func TestPrepareAuditPopulation(t *testing.T) {
	path := filepath.Join(t.TempDir(), "records.jsonl")
	records := []privateTraceRecord{{Index: 0, CaseID: "one", ActivityIDs: []int{5}, Salt: "01"}, {Index: 4, CaseID: "two", ActivityIDs: []int{5}, Salt: "02"}}
	writeRecords := func(records []privateTraceRecord) {
		t.Helper()
		var data []byte
		for _, record := range records {
			record.HashScheme = hashing.Scheme
			row, err := json.Marshal(record)
			if err != nil {
				t.Fatal(err)
			}
			data = append(data, row...)
			data = append(data, '\n')
		}
		if err := os.WriteFile(path, data, 0o600); err != nil {
			t.Fatal(err)
		}
	}
	writeRecords(records)
	root, all, _, err := PrepareAuditPopulation(path, nil)
	if err != nil || len(all) != 2 {
		t.Fatalf("all records: %v", err)
	}
	subsetRoot, subset, ids, err := PrepareAuditPopulation(path, []string{"two"})
	if err != nil || subsetRoot != root || len(subset) != 1 || subset[0] != all[1] || ids[4] != "two" {
		t.Fatalf("subset must retain full snapshot root: %v", err)
	}
	for _, selection := range [][]string{{"missing"}, {"two", "two"}, {""}} {
		if _, _, _, err := PrepareAuditPopulation(path, selection); err == nil {
			t.Fatal("invalid selection accepted")
		}
	}
	records[1].Index = 0
	writeRecords(records)
	if _, _, _, err := PrepareAuditPopulation(path, nil); err == nil {
		t.Fatal("duplicate index accepted")
	}
	records[1].Index = 4
	records[1].CaseID = "one"
	writeRecords(records)
	if _, _, _, err := PrepareAuditPopulation(path, nil); err == nil {
		t.Fatal("duplicate case accepted")
	}
}

// This uses genuine Groth16 proofs, serialization and public-only verification.
// Two commitments belong to the same snapshot. No private records are read by
// the verifier. Both fixtures share an activity sequence but have distinct salts
// and indices, representing two different agreed cases rather than a replay.
func TestAuditRealProofAccounting(t *testing.T) {
	a, b := realCaseAssignment(t, 1), realCaseAssignment(t, 1)
	b.TraceIndex = 12
	b.TraceSalt = big.NewInt(424243)
	var trace [MaxTraceEvents]int
	copy(trace[:], []int{5, 4, 6, 10, 3})
	b.TraceCommitment = ComputeTraceCommitment(5, trace, b.TraceSalt.(*big.Int))
	leafA := hashFieldElements(big.NewInt(DomainMerkleLeaf), big.NewInt(13), a.TraceCommitment.(*big.Int))
	leafB := hashFieldElements(big.NewInt(DomainMerkleLeaf), big.NewInt(12), b.TraceCommitment.(*big.Int))
	a.MerklePath[0], b.MerklePath[0] = leafB, leafA
	root := hashFieldElements(big.NewInt(DomainMerkleNode), leafB, leafA)
	for level := 1; level < MerkleTreeDepth; level++ {
		sibling := a.MerklePath[level].(*big.Int)
		if (13>>level)&1 == 0 {
			root = hashFieldElements(big.NewInt(int64(DomainMerkleNode+level)), root, sibling)
		} else {
			root = hashFieldElements(big.NewInt(int64(DomainMerkleNode+level)), sibling, root)
		}
	}
	a.EventLogRoot, b.EventLogRoot = root, root
	cs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &SingleTracePetriNetCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	pk, vk, err := groth16.Setup(cs)
	if err != nil {
		t.Fatal(err)
	}
	var vkBuffer bytes.Buffer
	if _, err := vk.WriteTo(&vkBuffer); err != nil {
		t.Fatal(err)
	}
	m := AuditManifest{Version: AuditVersion, Root: root.String(), VerificationKeyMiMC: hashing.VerificationKey(vkBuffer.Bytes()), Threshold: 1, TargetPercent: 95, Cases: []AuditCase{{13, a.TraceCommitment.(*big.Int).String()}, {12, b.TraceCommitment.(*big.Int).String()}}}
	encode := func(value any) []byte {
		t.Helper()
		data, err := json.Marshal(value)
		if err != nil {
			t.Fatal(err)
		}
		return data
	}
	manifestBytes := encode(m)
	digest := hashing.Manifest(manifestBytes)
	newVerifier := func(data []byte) *AuditVerifier {
		t.Helper()
		v, err := NewAuditVerifier(data, hashing.Manifest(data), vkBuffer.Bytes())
		if err != nil {
			t.Fatal(err)
		}
		return v
	}
	makeBundle := func(assignment *SingleTracePetriNetCircuit) AuditProofBundle {
		t.Helper()
		proof, _, err := GenerateGroth16Proof(cs, pk, assignment)
		if err != nil {
			t.Fatal(err)
		}
		var proofBuffer bytes.Buffer
		if _, err := proof.WriteTo(&proofBuffer); err != nil {
			t.Fatal(err)
		}
		return AuditProofBundle{ManifestMiMC: digest, Commitment: assignment.TraceCommitment.(*big.Int).String(), Proof: proofBuffer.Bytes()}
	}
	bundleA, bundleB := makeBundle(a), makeBundle(b)
	v := newVerifier(manifestBytes)
	if v.Report().Certified != 0 || v.Report().TargetMet {
		t.Fatal("empty submission certified")
	}
	v.Check("malformed.json", []byte("not json"))
	bad := bundleA
	bad.Proof = []byte{0}
	v.Check("invalid-proof.json", encode(bad))
	if v.Report().Certified != 0 {
		t.Fatal("invalid proof counted")
	}
	v.Check("a.json", encode(bundleA))
	v.Check("a-copy.json", encode(bundleA))
	r := v.Report()
	if r.Certified != 1 || r.Population != 2 || r.Uncertified != 1 || r.TargetMet || r.Receipts[3].Status != "duplicate" {
		t.Fatalf("duplicate/missing accounting wrong: %+v", r)
	}
	v.Check("b.json", encode(bundleB))
	if r = v.Report(); r.Certified != 2 || !r.TargetMet {
		t.Fatalf("two genuine proofs not certified: %+v", r)
	}
	for name, mutate := range map[string]func(*AuditProofBundle){
		"unexpected commitment": func(b *AuditProofBundle) { b.Commitment = "1" },
		"foreign audit":         func(b *AuditProofBundle) { b.ManifestMiMC = strings.Repeat("0", 64) },
		"wrong case proof":      func(b *AuditProofBundle) { b.Commitment = bundleB.Commitment },
		"truncated proof":       func(b *AuditProofBundle) { b.Proof = b.Proof[:5] },
		"trailing data":         func(b *AuditProofBundle) { b.Proof = append(append([]byte(nil), b.Proof...), 0) },
	} {
		t.Run(name, func(t *testing.T) {
			v := newVerifier(manifestBytes)
			b := bundleA
			mutate(&b)
			v.Check(name, encode(b))
			if v.Report().Certified != 0 {
				t.Fatal("invalid bundle certified")
			}
		})
	}
	// The public bundle and report must not disclose the exact cost. Reject
	// cost-bearing legacy bundles rather than silently ignoring their fields.
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(encode(bundleA), &fields); err != nil {
		t.Fatal(err)
	}
	if len(fields) != 3 || fields["cost"] != nil {
		t.Fatal("unexpected public bundle fields")
	}
	for _, name := range []string{"cost", "alignment_cost"} {
		t.Run("reject disclosed "+name, func(t *testing.T) {
			var disclosed map[string]json.RawMessage
			if err := json.Unmarshal(encode(bundleA), &disclosed); err != nil {
				t.Fatal(err)
			}
			disclosed[name] = json.RawMessage("1")
			v := newVerifier(manifestBytes)
			v.Check("legacy.json", encode(disclosed))
			if v.Report().Certified != 0 {
				t.Fatal("cost-bearing bundle accepted")
			}
		})
	}
	if bytes.Contains(encode(r), []byte(`"cost"`)) || bytes.Contains(encode(r), []byte(`"alignment_cost"`)) {
		t.Fatal("audit report reveals exact cost")
	}
	for name, mutate := range map[string]func(*AuditManifest){
		"different root":      func(m *AuditManifest) { m.Root = "1" },
		"different threshold": func(m *AuditManifest) { m.Threshold = 2 },
	} {
		t.Run(name, func(t *testing.T) {
			changed := m
			mutate(&changed)
			data := encode(changed)
			v := newVerifier(data)
			b := bundleA
			b.ManifestMiMC = hashing.Manifest(data)
			v.Check(name, encode(b))
			if v.Report().Certified != 0 {
				t.Fatal("proof accepted under changed public context")
			}
		})
	}
	if _, err := NewAuditVerifier(append(manifestBytes, ' '), digest, vkBuffer.Bytes()); err == nil {
		t.Fatal("changed manifest accepted under original pin")
	}
	if _, err := NewAuditVerifier(manifestBytes, "", vkBuffer.Bytes()); err == nil {
		t.Fatal("missing pin accepted")
	}
	if _, err := NewAuditVerifier(manifestBytes, digest, append(vkBuffer.Bytes(), 0)); err == nil {
		t.Fatal("changed key accepted")
	}
}
