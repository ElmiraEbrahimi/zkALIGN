package circuit

import (
	"math/big"
	"testing"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"
	"github.com/consensys/gnark/test"
)

func realCaseAssignment(t *testing.T, threshold int) *SingleTracePetriNetCircuit {
	t.Helper()
	traceValues := []int{5, 4, 6, 10, 3}
	moveTypes := []int{3, 3, 3, 3, 1, 3, 1, 1, 3, 3, 3, 3, 1, 1, 3, 3, 3, 3}
	activities := []int{0, 0, 0, 0, 5, 0, 4, 6, 0, 0, 0, 0, 10, 3, 0, 0, 0, 0}
	transitions := []int{34, 7, 35, 19, 2, 22, 14, 6, 32, 23, 31, 26, 5, 12, 33, 27, 28, 29}
	salt := big.NewInt(424242)
	assignment := &SingleTracePetriNetCircuit{
		TraceLength:     len(traceValues),
		TraceSalt:       salt,
		TraceIndex:      13,
		AlignmentLength: len(moveTypes),
		AlignmentCost:   1,
		CostThreshold:   threshold,
	}
	var integerTrace [MaxTraceEvents]int
	for index := 0; index < MaxTraceEvents; index++ {
		assignment.TraceEvents[index] = 0
	}
	for index, activityID := range traceValues {
		integerTrace[index] = activityID
		assignment.TraceEvents[index] = activityID
	}
	for index := 0; index < MaxAlignmentMoves; index++ {
		assignment.AlignmentMoveTypes[index] = MovePadding
		assignment.AlignmentActivities[index] = 0
		assignment.ModelTransitionIDs[index] = 0
	}
	for index := range moveTypes {
		assignment.AlignmentMoveTypes[index] = moveTypes[index]
		assignment.AlignmentActivities[index] = activities[index]
		assignment.ModelTransitionIDs[index] = transitions[index]
	}
	assignment.TraceCommitment = ComputeTraceCommitment(len(traceValues), integerTrace, salt)

	currentHash := hashFieldElements(big.NewInt(DomainMerkleLeaf), big.NewInt(13), assignment.TraceCommitment.(*big.Int))
	defaultHash := hashFieldElements(big.NewInt(DomainMerkleLeaf), big.NewInt(0), big.NewInt(0))
	for level := 0; level < MerkleTreeDepth; level++ {
		assignment.MerklePath[level] = defaultHash
		if (13>>level)&1 == 0 {
			currentHash = hashFieldElements(big.NewInt(int64(DomainMerkleNode+level)), currentHash, defaultHash)
		} else {
			currentHash = hashFieldElements(big.NewInt(int64(DomainMerkleNode+level)), defaultHash, currentHash)
		}
		defaultHash = hashFieldElements(big.NewInt(int64(DomainMerkleNode+level)), defaultHash, defaultHash)
	}
	assignment.EventLogRoot = currentHash
	return assignment
}

func TestRealSepsisWitnessSolvesCircuit(t *testing.T) {
	assignment := realCaseAssignment(t, 1)
	if err := test.IsSolved(&SingleTracePetriNetCircuit{}, assignment, ecc.BN254.ScalarField()); err != nil {
		t.Fatal(err)
	}
}

func TestRealSepsisGroth16ProofVerifies(t *testing.T) {
	assignment := realCaseAssignment(t, 1)
	constraintSystem, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &SingleTracePetriNetCircuit{})
	if err != nil {
		t.Fatal(err)
	}
	provingKey, verifyingKey, err := groth16.Setup(constraintSystem)
	if err != nil {
		t.Fatal(err)
	}
	proof, publicWitness, err := GenerateGroth16Proof(constraintSystem, provingKey, assignment)
	if err != nil {
		t.Fatal(err)
	}
	if err := VerifyGroth16Proof(proof, verifyingKey, publicWitness); err != nil {
		t.Fatal(err)
	}
}

func TestCostAboveThresholdIsRejected(t *testing.T) {
	assignment := realCaseAssignment(t, 0)
	if err := test.IsSolved(&SingleTracePetriNetCircuit{}, assignment, ecc.BN254.ScalarField()); err == nil {
		t.Fatal("expected cost 1 above threshold 0 to be rejected")
	}
}

func TestFalsePublicCostIsRejected(t *testing.T) {
	assignment := realCaseAssignment(t, 1)
	assignment.AlignmentCost = 0
	if err := test.IsSolved(&SingleTracePetriNetCircuit{}, assignment, ecc.BN254.ScalarField()); err == nil {
		t.Fatal("expected false public cost to be rejected")
	}
}

func TestChangedCommittedTraceIsRejected(t *testing.T) {
	assignment := realCaseAssignment(t, 1)
	assignment.TraceEvents[0] = 4
	if err := test.IsSolved(&SingleTracePetriNetCircuit{}, assignment, ecc.BN254.ScalarField()); err == nil {
		t.Fatal("expected a changed committed trace to be rejected")
	}
}

func TestWrongEventLogMembershipPathIsRejected(t *testing.T) {
	assignment := realCaseAssignment(t, 1)
	assignment.MerklePath[0] = 12345
	if err := test.IsSolved(&SingleTracePetriNetCircuit{}, assignment, ecc.BN254.ScalarField()); err == nil {
		t.Fatal("expected a wrong event-log membership path to be rejected")
	}
}

func TestAlignmentTraceMismatchIsRejected(t *testing.T) {
	assignment := realCaseAssignment(t, 1)
	assignment.AlignmentActivities[4] = 4
	if err := test.IsSolved(&SingleTracePetriNetCircuit{}, assignment, ecc.BN254.ScalarField()); err == nil {
		t.Fatal("expected an alignment/trace mismatch to be rejected")
	}
}

func TestIllegalModelTransitionIsRejected(t *testing.T) {
	assignment := realCaseAssignment(t, 1)
	assignment.ModelTransitionIDs[0] = 1
	if err := test.IsSolved(&SingleTracePetriNetCircuit{}, assignment, ecc.BN254.ScalarField()); err == nil {
		t.Fatal("expected an illegal Petri-net transition to be rejected")
	}
}

func TestIncompleteAlignmentIsRejected(t *testing.T) {
	assignment := realCaseAssignment(t, 1)
	assignment.AlignmentLength = 17
	assignment.AlignmentMoveTypes[17] = MovePadding
	assignment.AlignmentActivities[17] = 0
	assignment.ModelTransitionIDs[17] = 0
	if err := test.IsSolved(&SingleTracePetriNetCircuit{}, assignment, ecc.BN254.ScalarField()); err == nil {
		t.Fatal("expected an alignment that does not reach the final marking to be rejected")
	}
}
