package circuit

import (
	"encoding/json"
	"fmt"
	"github.com/consensys/gnark/frontend"
	"os"
)

// Incidence lists contain zero-based transition offsets. Witness transition IDs
// are one-based. Labels 1..ActivityCount are visible and zero is silent.
type ModelConfig struct {
	ActivityCount     int     `json:"activity_count"`
	TraceCapacity     int     `json:"trace_capacity"`
	AlignmentCapacity int     `json:"alignment_capacity"`
	Initial           []int   `json:"initial"`
	Final             []int   `json:"final"`
	Labels            []int   `json:"labels"`
	ModelCosts        []int   `json:"model_costs"`
	Inputs            [][]int `json:"inputs"`
	Outputs           [][]int `json:"outputs"`
}

func SepsisConfig() *ModelConfig {
	return &ModelConfig{ActivityCount, MaxTraceEvents, MaxAlignmentMoves,
		append([]int(nil), sepsisInitialMarking[:]...), append([]int(nil), sepsisFinalMarking[:]...),
		append([]int(nil), sepsisTransitionLabels[:]...), append([]int(nil), sepsisTransitionModelCosts[:]...),
		sepsisInputTransitionsByPlace, sepsisOutputTransitionsByPlace}
}

func LoadModelConfig(path string) (*ModelConfig, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var cfg ModelConfig
	if err = json.Unmarshal(data, &cfg); err != nil {
		return nil, err
	}
	return &cfg, cfg.Validate()
}

func (c *ModelConfig) Validate() error {
	if c == nil || c.ActivityCount < 1 || c.TraceCapacity < 1 || c.AlignmentCapacity < 1 {
		return fmt.Errorf("positive activity count and capacities required")
	}
	if len(c.Initial) == 0 || len(c.Labels) == 0 || len(c.Final) != len(c.Initial) ||
		len(c.Inputs) != len(c.Initial) || len(c.Outputs) != len(c.Initial) || len(c.ModelCosts) != len(c.Labels) {
		return fmt.Errorf("inconsistent model dimensions")
	}
	for p := range c.Initial {
		if (c.Initial[p] != 0 && c.Initial[p] != 1) || (c.Final[p] != 0 && c.Final[p] != 1) {
			return fmt.Errorf("markings must be Boolean")
		}
		for _, list := range [][]int{c.Inputs[p], c.Outputs[p]} {
			seen := map[int]bool{}
			for _, t := range list {
				if t < 0 || t >= len(c.Labels) || seen[t] {
					return fmt.Errorf("invalid or repeated incidence offset")
				}
				seen[t] = true
			}
		}
	}
	for t, label := range c.Labels {
		if label < 0 || label > c.ActivityCount {
			return fmt.Errorf("invalid transition label")
		}
		want := 0
		if label != 0 {
			want = 1
		}
		if c.ModelCosts[t] != want {
			return fmt.Errorf("only the fixed unit deviation policy is supported")
		}
	}
	return nil
}

func NewConfiguredCircuit(cfg *ModelConfig) *ConfiguredCircuit {
	return &ConfiguredCircuit{Config: cfg, TraceEvents: make([]frontend.Variable, cfg.TraceCapacity),
		AlignmentMoveTypes:  make([]frontend.Variable, cfg.AlignmentCapacity),
		AlignmentActivities: make([]frontend.Variable, cfg.AlignmentCapacity),
		ModelTransitionIDs:  make([]frontend.Variable, cfg.AlignmentCapacity)}
}
