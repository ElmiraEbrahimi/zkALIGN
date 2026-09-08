package circuit

import (
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/test"
)

func validAssignment() AlignmentCircuit {
	trace := [MaxTrace]int{1, 2, 6, 4, 5, 0, 0, 0}
	return AlignmentCircuit{
		TraceCommitment: TraceCommitment(5, trace, 424242),
		Threshold:       2,
		ClaimedCost:     2,
		TraceLength:     5,
		Trace:           [MaxTrace]frontend.Variable{1, 2, 6, 4, 5, 0, 0, 0},
		Salt:            424242,
		MoveType:        [MaxMoves]frontend.Variable{MoveSync, MoveSync, MoveLog, MoveModel, MoveSync, MoveSync, MovePad, MovePad, MovePad, MovePad},
		LogActivity:     [MaxMoves]frontend.Variable{1, 2, 6, 0, 4, 5, 0, 0, 0, 0},
		Transition:      [MaxMoves]frontend.Variable{1, 2, 0, 3, 4, 5, 0, 0, 0, 0},
	}
}

func TestValidWitnessSolvesCircuit(t *testing.T) {
	assignment := validAssignment()
	if err := test.IsSolved(&AlignmentCircuit{}, &assignment, ecc.BN254.ScalarField()); err != nil {
		t.Fatal(err)
	}
}

func TestGroth16ProofVerifies(t *testing.T) {
	assignment := validAssignment()
	constraintSystem, err := frontend.Compile(
		ecc.BN254.ScalarField(), r1cs.NewBuilder, &AlignmentCircuit{},
	)
	if err != nil {
		t.Fatal(err)
	}
	provingKey, verifyingKey, err := groth16.Setup(constraintSystem)
	if err != nil {
		t.Fatal(err)
	}
	witness, err := frontend.NewWitness(&assignment, ecc.BN254.ScalarField())
	if err != nil {
		t.Fatal(err)
	}
	proof, err := groth16.Prove(constraintSystem, provingKey, witness)
	if err != nil {
		t.Fatal(err)
	}
	publicWitness, err := witness.Public()
	if err != nil {
		t.Fatal(err)
	}
	if err := groth16.Verify(proof, verifyingKey, publicWitness); err != nil {
		t.Fatal(err)
	}
}

func TestFalseCostIsRejected(t *testing.T) {
	assignment := validAssignment()
	assignment.ClaimedCost = 1
	if err := test.IsSolved(&AlignmentCircuit{}, &assignment, ecc.BN254.ScalarField()); err == nil {
		t.Fatal("expected false cost to be rejected")
	}
}

func TestChangedCommittedTraceIsRejected(t *testing.T) {
	assignment := validAssignment()
	assignment.Trace[2] = 3
	if err := test.IsSolved(&AlignmentCircuit{}, &assignment, ecc.BN254.ScalarField()); err == nil {
		t.Fatal("expected changed trace to be rejected")
	}
}
