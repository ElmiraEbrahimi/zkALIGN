package circuit

import (
	"github.com/consensys/gnark/frontend"
)

const (
	// These dimensions describe the real Petri net exported by the PM4Py
	// pipeline. Changing the discovered model requires regenerating
	// sepsis_model_gen.go and recompiling the circuit and Groth16 keys.
	PlaceCount        = 27
	TransitionCount   = 35
	ActivityCount     = 16
	MaxTraceEvents    = 185
	MaxAlignmentMoves = 64
	MerkleTreeDepth   = 32
	DomainTraceV2     = 20260910
	DomainMerkleLeaf  = 20260911
	DomainMerkleNode  = 20260912
)

const (
	// Zero is reserved for padding so unused fixed-array positions cannot be
	// confused with a real alignment move.
	MovePadding = iota
	MoveSynchronous
	MoveLogOnly
	MoveModelOnly
)

// SingleTracePetriNetCircuit proves that one private healthcare trace has a
// valid, complete alignment against the fixed public Sepsis Petri net.
type SingleTracePetriNetCircuit struct {
	// Public values are visible to the verifier. TraceCommitment hides the
	// salted trace; EventLogRoot binds it to the committed hospital log.
	TraceCommitment frontend.Variable `gnark:",public"`
	EventLogRoot    frontend.Variable `gnark:",public"`
	CostThreshold   frontend.Variable `gnark:",public"`

	// The exact cost is private. Goals 5 and 6 still recompute it from the
	// alignment and prove it is at most the public threshold.
	AlignmentCost frontend.Variable

	// These fields are secret witness values. TraceEvents contains numeric
	// activity IDs 1..16 followed by zero padding up to MaxTraceEvents.
	TraceLength frontend.Variable
	TraceEvents [MaxTraceEvents]frontend.Variable
	TraceSalt   frontend.Variable
	TraceIndex  frontend.Variable
	MerklePath  [MerkleTreeDepth]frontend.Variable

	// Each alignment position is one parallel row across these arrays:
	// move type, consumed trace activity (or zero), and selected Petri-net
	// transition ID (or zero). Positions after AlignmentLength are all zero.
	AlignmentLength     frontend.Variable
	AlignmentMoveTypes  [MaxAlignmentMoves]frontend.Variable
	AlignmentActivities [MaxAlignmentMoves]frontend.Variable
	ModelTransitionIDs  [MaxAlignmentMoves]frontend.Variable
}

func (c *SingleTracePetriNetCircuit) Define(api frontend.API) error {
	return c.Configured().Define(api)
}

// Configured shares the constraint implementation while preserving the original
// public/secret field order and legacy command interface.
func (c *SingleTracePetriNetCircuit) Configured() *ConfiguredCircuit {
	return &ConfiguredCircuit{
		Config:          SepsisConfig(),
		TraceCommitment: c.TraceCommitment, EventLogRoot: c.EventLogRoot, CostThreshold: c.CostThreshold,
		AlignmentCost: c.AlignmentCost, TraceLength: c.TraceLength, TraceEvents: c.TraceEvents[:],
		TraceSalt: c.TraceSalt, TraceIndex: c.TraceIndex, MerklePath: c.MerklePath,
		AlignmentLength: c.AlignmentLength, AlignmentMoveTypes: c.AlignmentMoveTypes[:],
		AlignmentActivities: c.AlignmentActivities[:], ModelTransitionIDs: c.ModelTransitionIDs[:],
	}
}
