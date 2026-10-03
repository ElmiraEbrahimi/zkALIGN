// zkalign-audit verifies an agreed population using separate single-trace proofs.
package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"github.com/ElmiraEbrahimi/zkALIGN/hashing"
	"io"
	"log"
	"math/big"
	"os"
	"path/filepath"
	"strings"

	"github.com/ElmiraEbrahimi/zkALIGN/circuit"
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
)

const defaultRecords = "outputs/sepsis/commitment_log/private_trace_records.jsonl"
const defaultWitnesses = "outputs/sepsis/alignment_witnesses.json"

var errTargetUnmet = errors.New("audit target not established")

func main() {
	if len(os.Args) < 2 {
		log.Fatal("usage: zkalign-audit init|prove|verify [flags]")
	}
	var err error
	switch os.Args[1] {
	case "init":
		err = initialize(os.Args[2:])
	case "prove":
		err = prove(os.Args[2:])
	case "verify":
		err = verify(os.Args[2:])
	default:
		err = fmt.Errorf("unknown command %q", os.Args[1])
	}
	if errors.Is(err, errTargetUnmet) {
		os.Exit(2)
	}
	if err != nil {
		log.Fatal(err)
	}
}

// Never silently replace a pinned context, key or proof with a different one.
func writeNew(path string, data []byte, mode os.FileMode) error {
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, mode)
	if err != nil {
		return err
	}
	_, err = f.Write(data)
	closeErr := f.Close()
	if err != nil {
		return err
	}
	return closeErr
}

func marshal(value any) ([]byte, error) { return json.MarshalIndent(value, "", "  ") }

func serialize(value io.WriterTo) ([]byte, error) {
	var buffer bytes.Buffer
	_, err := value.WriteTo(&buffer)
	return buffer.Bytes(), err
}

func initialize(args []string) error {
	flags := flag.NewFlagSet("init", flag.ContinueOnError)
	out := flags.String("out", "outputs/sepsis/audit", "new directory for shared keys and proposed audit manifest")
	records := flags.String("records", defaultRecords, "private trace records")
	threshold := flags.Int("threshold", 1, "shared maximum unit alignment cost")
	target := flags.Int("target", 95, "required percentage, 1..100")
	if err := flags.Parse(args); err != nil {
		return err
	}
	root, population, _, err := circuit.PrepareAuditPopulation(*records)
	if err != nil {
		return err
	}
	manifest := circuit.AuditManifest{Version: circuit.AuditVersion, Root: root, Threshold: *threshold, TargetPercent: *target, Cases: population, VerificationKeyMiMC: strings.Repeat("0", 64)}
	if err := manifest.Validate(); err != nil {
		return err
	}
	if _, err := os.Stat(*out); !os.IsNotExist(err) {
		return fmt.Errorf("output directory must not already exist: %s", *out)
	}
	cs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &circuit.SingleTracePetriNetCircuit{})
	if err != nil {
		return err
	}
	fmt.Printf("Setting up one shared circuit with %d constraints for %d agreed traces.\n", cs.GetNbConstraints(), len(population))
	pk, vk, err := groth16.Setup(cs)
	if err != nil {
		return err
	}
	pkBytes, err := serialize(pk)
	if err != nil {
		return err
	}
	vkBytes, err := serialize(vk)
	if err != nil {
		return err
	}
	manifest.VerificationKeyMiMC = hashing.VerificationKey(vkBytes)
	manifestBytes, err := marshal(manifest)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(*out, 0o700); err != nil {
		return err
	}
	if err := writeNew(filepath.Join(*out, "proving.key"), pkBytes, 0o600); err != nil {
		return err
	}
	if err := writeNew(filepath.Join(*out, "verification.key"), vkBytes, 0o644); err != nil {
		return err
	}
	if err := writeNew(filepath.Join(*out, "manifest.json"), manifestBytes, 0o644); err != nil {
		return err
	}
	digest := hashing.Manifest(manifestBytes)
	if err := writeNew(filepath.Join(*out, "manifest.mimc"), []byte(digest+"\n"), 0o644); err != nil {
		return err
	}
	fmt.Printf("PROPOSED AUDIT: N=%d, K=%d, target=%d%%.\nManifest MiMC: %s\n", len(population), *threshold, *target, digest)
	fmt.Println("Before proofs are accepted, the auditor must independently approve the population, snapshot, model/circuit, setup/key and threshold, then retain this digest. Local setup is a demonstration, not a trusted-setup ceremony.")
	return nil
}

func prove(args []string) error {
	flags := flag.NewFlagSet("prove", flag.ContinueOnError)
	dir := flags.String("audit", "outputs/sepsis/audit", "directory containing shared keys and manifest")
	records := flags.String("records", defaultRecords, "private trace records")
	witnesses := flags.String("witnesses", defaultWitnesses, "private saved alignment witnesses")
	if err := flags.Parse(args); err != nil {
		return err
	}
	manifestBytes, err := os.ReadFile(filepath.Join(*dir, "manifest.json"))
	if err != nil {
		return err
	}
	vkBytes, err := os.ReadFile(filepath.Join(*dir, "verification.key"))
	if err != nil {
		return err
	}
	digest := hashing.Manifest(manifestBytes)
	manifest, vk, err := circuit.LoadAuditContext(manifestBytes, digest, vkBytes)
	if err != nil {
		return err
	}
	root, population, ids, err := circuit.PrepareAuditPopulation(*records)
	if err != nil {
		return err
	}
	if root != manifest.Root {
		return fmt.Errorf("private store differs from pinned snapshot")
	}
	stored := map[uint32]string{}
	for _, entry := range population {
		stored[entry.Index] = entry.Commitment
	}
	for _, entry := range manifest.Cases {
		if stored[entry.Index] != entry.Commitment {
			return fmt.Errorf("manifest entry differs from private store")
		}
	}
	pkFile, err := os.Open(filepath.Join(*dir, "proving.key"))
	if err != nil {
		return err
	}
	defer pkFile.Close()
	pk := groth16.NewProvingKey(ecc.BN254)
	if _, err := pk.ReadFrom(pkFile); err != nil {
		return err
	}
	cs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &circuit.SingleTracePetriNetCircuit{})
	if err != nil {
		return err
	}
	proofDir := filepath.Join(*dir, "proofs")
	if err := os.MkdirAll(proofDir, 0o755); err != nil {
		return err
	}
	generated, unresolved := 0, 0
	for _, entry := range manifest.Cases {
		name := filepath.Join(proofDir, fmt.Sprintf("trace-%d.json", entry.Index))
		if _, err := os.Stat(name); err == nil {
			fmt.Printf("Existing proof file retained for index %d; the verifier will check it.\n", entry.Index)
			continue
		} else if !os.IsNotExist(err) {
			return err
		}
		assignment, summary, err := circuit.LoadRealAlignmentAssignment(*witnesses, *records, ids[entry.Index], manifest.Threshold)
		if err == nil && (summary.TraceIndex != int(entry.Index) || assignment.TraceCommitment.(*big.Int).String() != entry.Commitment || assignment.EventLogRoot.(*big.Int).String() != manifest.Root) {
			err = fmt.Errorf("alignment witness does not match agreed trace")
		}
		if err == nil && summary.AlignmentCost > manifest.Threshold {
			err = fmt.Errorf("candidate cost exceeds K=%d; this does not prove that no cheaper alignment exists", manifest.Threshold)
		}
		if err != nil {
			unresolved++
			fmt.Printf("UNCERTIFIED index %d: %v\n", entry.Index, err)
			continue
		}
		proof, public, err := circuit.GenerateGroth16Proof(cs, pk, assignment)
		if err != nil {
			unresolved++
			fmt.Printf("UNCERTIFIED index %d: %v\n", entry.Index, err)
			continue
		}
		if err := circuit.VerifyGroth16Proof(proof, vk, public); err != nil {
			return fmt.Errorf("generated proof failed verification under shared key: %w", err)
		}
		proofBytes, err := serialize(proof)
		if err != nil {
			return err
		}
		bundleBytes, err := marshal(circuit.AuditProofBundle{ManifestMiMC: digest, Commitment: entry.Commitment, Proof: proofBytes})
		if err != nil {
			return err
		}
		if err := writeNew(name, bundleBytes, 0o644); err != nil {
			return err
		}
		generated++
		fmt.Printf("Proof generated and locally verified for index %d: cost <= %d (exact cost private).\n", entry.Index, manifest.Threshold)
	}
	fmt.Printf("Generated %d separate proofs; %d unresolved this run. The agreed denominator remains %d. Run the independent verify command.\n", generated, unresolved, len(manifest.Cases))
	return nil
}

func verify(args []string) error {
	flags := flag.NewFlagSet("verify", flag.ContinueOnError)
	manifestPath := flags.String("manifest", "", "public manifest file")
	approvedDigest := flags.String("pin", "", "manifest MiMC independently retained by the auditor (required)")
	vkPath := flags.String("vk", "", "approved public verification key")
	proofDir := flags.String("proofs", "", "directory of public JSON proof bundles")
	reportPath := flags.String("report", "", "optional NEW JSON report file")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if *manifestPath == "" || *approvedDigest == "" || *vkPath == "" || *proofDir == "" {
		return fmt.Errorf("verify requires -manifest, -pin, -vk and -proofs; no private files are used")
	}
	manifestBytes, err := os.ReadFile(*manifestPath)
	if err != nil {
		return err
	}
	vkBytes, err := os.ReadFile(*vkPath)
	if err != nil {
		return err
	}
	verifier, err := circuit.NewAuditVerifier(manifestBytes, *approvedDigest, vkBytes)
	if err != nil {
		return err
	}
	files, err := os.ReadDir(*proofDir)
	if err != nil {
		return err
	}
	for _, file := range files {
		if file.IsDir() || filepath.Ext(file.Name()) != ".json" {
			continue
		}
		data, err := os.ReadFile(filepath.Join(*proofDir, file.Name()))
		if err != nil {
			return err
		}
		verifier.Check(file.Name(), data)
	}
	report := verifier.Report()
	if *reportPath != "" {
		data, err := marshal(report)
		if err != nil {
			return err
		}
		if err := writeNew(*reportPath, data, 0o644); err != nil {
			return err
		}
	}
	for _, receipt := range report.Receipts {
		if receipt.Status != "accepted" {
			fmt.Printf("%s: %s (%s)\n", receipt.File, receipt.Status, receipt.Reason)
		}
	}
	fmt.Printf("CERTIFIED: %d/%d agreed traces (%.2f%%). Required: %d for target %d%% at K=%d.\n", report.Certified, report.Population, 100*float64(report.Certified)/float64(report.Population), report.Required, report.TargetPercent, report.Threshold)
	fmt.Printf("UNCERTIFIED: %d. Missing/invalid proofs do not establish nonconformance.\n", report.Uncertified)
	if report.TargetMet {
		fmt.Printf("AUDIT TARGET MET: at least %d%% of the agreed traces admit a valid, complete alignment with cost <= %d.\n", report.TargetPercent, report.Threshold)
		return nil
	}
	fmt.Println("AUDIT TARGET NOT ESTABLISHED. This is not proof that the population violates the policy.")
	return errTargetUnmet
}
