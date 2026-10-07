package circuit

import (
	"fmt"
	"github.com/consensys/gnark/frontend"
	"math/big"
)

// EvaluationCase is private input to the evaluation adapter, never an audit
// submission. The original source data is public research data, not patient data.
type EvaluationMove struct {
	Type       int `json:"type"`
	Activity   int `json:"activity"`
	Transition int `json:"transition"`
}
type EvaluationCase struct {
	CaseID     string           `json:"case_id"`
	Index      uint32           `json:"index"`
	Events     []int            `json:"events"`
	Salt       string           `json:"salt"`
	Moves      []EvaluationMove `json:"moves"`
	Cost       *int             `json:"cost"`
	Status     string           `json:"status"`
	Commitment string           `json:"commitment"`
	Root       string           `json:"root"`
	Path       []string         `json:"path"`
}

func ConfiguredCommitment(cfg *ModelConfig, events []int, salt *big.Int) (*big.Int, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	if len(events) > cfg.TraceCapacity || salt == nil || salt.Sign() < 0 {
		return nil, fmt.Errorf("invalid trace capacity or salt")
	}
	fields := []*big.Int{big.NewInt(DomainTraceV2), big.NewInt(int64(len(events)))}
	for j := 0; j < cfg.TraceCapacity; j++ {
		a := 0
		if j < len(events) {
			a = events[j]
			if a < 1 || a > cfg.ActivityCount {
				return nil, fmt.Errorf("invalid activity")
			}
		}
		fields = append(fields, big.NewInt(int64(a)))
	}
	fields = append(fields, salt)
	return hashFieldElements(fields...), nil
}

// PrepareConfiguredPopulation reuses the protocol's indexed-leaf/default-tree
// implementation. Every provided record, including alignment failures, is bound.
func PrepareConfiguredPopulation(cfg *ModelConfig, cases []EvaluationCase) ([]EvaluationCase, []AuditCase, string, error) {
	if len(cases) == 0 {
		return nil, nil, "", fmt.Errorf("empty population")
	}
	leaves := map[uint32]*big.Int{}
	roster := make([]AuditCase, len(cases))
	ids := map[string]bool{}
	for j := range cases {
		c := &cases[j]
		if c.Index != uint32(j) || c.CaseID == "" || ids[c.CaseID] {
			return nil, nil, "", fmt.Errorf("noncontiguous or duplicate case")
		}
		ids[c.CaseID] = true
		salt, err := canonicalField(c.Salt)
		if err != nil {
			return nil, nil, "", err
		}
		commit, err := ConfiguredCommitment(cfg, c.Events, salt)
		if err != nil {
			return nil, nil, "", err
		}
		c.Commitment = commit.String()
		roster[j] = AuditCase{c.Index, c.Commitment}
		leaves[c.Index] = circuitMerkleLeaf(c.Index, commit)
	}
	for j := range cases {
		proof := buildCircuitMerkleProof(leaves, cases[j].Index)
		cases[j].Root = proof.Root.String()
		cases[j].Path = make([]string, MerkleTreeDepth)
		for l := range cases[j].Path {
			cases[j].Path[l] = proof.Siblings[l].String()
		}
	}
	return cases, roster, cases[0].Root, nil
}

func (c EvaluationCase) Assignment(cfg *ModelConfig, k int) (*ConfiguredCircuit, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	if k < 0 || c.Cost == nil || c.Status != "aligned" {
		return nil, fmt.Errorf("missing alignment or invalid threshold")
	}
	if len(c.Events) > cfg.TraceCapacity || len(c.Moves) > cfg.AlignmentCapacity {
		return nil, fmt.Errorf("capacity")
	}
	if len(c.Path) != MerkleTreeDepth {
		return nil, fmt.Errorf("incorrect Merkle path length")
	}
	a := NewConfiguredCircuit(cfg)
	a.TraceLength = len(c.Events)
	a.TraceSalt = c.Salt
	a.TraceIndex = c.Index
	a.TraceCommitment = c.Commitment
	a.EventLogRoot = c.Root
	a.AlignmentLength = len(c.Moves)
	a.AlignmentCost = *c.Cost
	a.CostThreshold = k
	for j := range a.TraceEvents {
		a.TraceEvents[j] = 0
	}
	for j, v := range c.Events {
		a.TraceEvents[j] = v
	}
	for j := range a.MerklePath {
		a.MerklePath[j] = c.Path[j]
	}
	for j := range a.AlignmentMoveTypes {
		a.AlignmentMoveTypes[j] = 0
		a.AlignmentActivities[j] = 0
		a.ModelTransitionIDs[j] = 0
	}
	for j, m := range c.Moves {
		a.AlignmentMoveTypes[j] = m.Type
		a.AlignmentActivities[j] = m.Activity
		a.ModelTransitionIDs[j] = m.Transition
	}
	return a, nil
}

// PublicAssignment intentionally has the same three fields and order as both
// circuit schemas; no private slices or model constants are needed by a verifier.
type PublicAssignment struct {
	TraceCommitment frontend.Variable `gnark:",public"`
	EventLogRoot    frontend.Variable `gnark:",public"`
	CostThreshold   frontend.Variable `gnark:",public"`
}

func (*PublicAssignment) Define(frontend.API) error { return nil }
