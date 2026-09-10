package circuit

import (
	"fmt"

	"github.com/consensys/gnark/backend/groth16"
	backendwitness "github.com/consensys/gnark/backend/witness"
	"github.com/consensys/gnark/constraint"
	"github.com/consensys/gnark/frontend"
)

// GenerateGroth16Proof creates a proof from the private assignment.
func GenerateGroth16Proof(constraintSystem constraint.ConstraintSystem, provingKey groth16.ProvingKey, assignment *SingleTracePetriNetCircuit) (groth16.Proof, backendwitness.Witness, error) {
	witness, err := frontend.NewWitness(assignment, constraintSystem.Field())
	if err != nil {
		return nil, nil, fmt.Errorf("build private witness: %w", err)
	}
	proof, err := groth16.Prove(constraintSystem, provingKey, witness)
	if err != nil {
		return nil, nil, fmt.Errorf("generate Groth16 proof: %w", err)
	}
	publicWitness, err := witness.Public()
	if err != nil {
		return nil, nil, fmt.Errorf("extract public witness: %w", err)
	}
	return proof, publicWitness, nil
}

// VerifyGroth16Proof is the verifier boundary: it receives only a proof,
// verifying key and public witness, never the private trace or alignment.
func VerifyGroth16Proof(proof groth16.Proof, verifyingKey groth16.VerifyingKey, publicWitness backendwitness.Witness) error {
	if err := groth16.Verify(proof, verifyingKey, publicWitness); err != nil {
		return fmt.Errorf("verify Groth16 proof: %w", err)
	}
	return nil
}
