package main

import (
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"

	"github.com/ElmiraEbrahimi/zkALIGN/circuit"
	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
)

func main() {
	witnessPath := flag.String("witnesses", "outputs/sepsis/alignment_witnesses.json", "PM4Py alignment witness JSON")
	recordsPath := flag.String("records", "outputs/sepsis/commitment_log/private_trace_records.jsonl", "private committed trace records")
	caseID := flag.String("case", "AG", "real held-out Sepsis case ID")
	threshold := flag.Int("threshold", 1, "maximum accepted unit alignment cost")
	proofPath := flag.String("proof", "outputs/sepsis/proofs/single_trace.groth16", "output proof file")
	flag.Parse()

	assignment, summary, err := circuit.LoadRealAlignmentAssignment(*witnessPath, *recordsPath, *caseID, *threshold)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("Preparing real Sepsis case %s (trace index %d): %d events, %d alignment moves.\n", summary.CaseID, summary.TraceIndex, summary.TraceLength, summary.AlignmentLength)

	constraintSystem, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &circuit.SingleTracePetriNetCircuit{})
	if err != nil {
		log.Fatalf("compile real Petri-net circuit: %v", err)
	}
	fmt.Printf("Compiled SingleTracePetriNetCircuit with %d constraints.\n", constraintSystem.GetNbConstraints())

	provingKey, verifyingKey, err := groth16.Setup(constraintSystem)
	if err != nil {
		log.Fatalf("Groth16 setup: %v", err)
	}
	proof, publicWitness, err := circuit.GenerateGroth16Proof(constraintSystem, provingKey, assignment)
	if err != nil {
		log.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Dir(*proofPath), 0o755); err != nil {
		log.Fatalf("create proof directory: %v", err)
	}
	proofFile, err := os.Create(*proofPath)
	if err != nil {
		log.Fatalf("create proof file: %v", err)
	}
	if _, err := proof.WriteTo(proofFile); err != nil {
		_ = proofFile.Close()
		log.Fatalf("write proof: %v", err)
	}
	if err := proofFile.Close(); err != nil {
		log.Fatalf("close proof file: %v", err)
	}

	if err := circuit.VerifyGroth16Proof(proof, verifyingKey, publicWitness); err != nil {
		log.Fatal(err)
	}
	fmt.Printf("PROOF VERIFIED SUCCESSFULLY: case %s has a valid, complete alignment with cost %d, which is within threshold %d.\n", summary.CaseID, summary.AlignmentCost, summary.CostThreshold)
	fmt.Printf("Proof written to %s. The verifier used only the proof and public inputs.\n", *proofPath)
}
