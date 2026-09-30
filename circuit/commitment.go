package circuit

import (
	"math/big"

	"github.com/ElmiraEbrahimi/zkALIGN/hashing"
)

// ComputeTraceCommitment mirrors the field-element sequence hashed in Define.
func ComputeTraceCommitment(traceLength int, trace [MaxTraceEvents]int, salt *big.Int) *big.Int {
	values := []*big.Int{big.NewInt(DomainTraceV2), big.NewInt(int64(traceLength))}
	for _, activity := range trace {
		values = append(values, big.NewInt(int64(activity)))
	}
	values = append(values, salt)
	return hashFieldElements(values...)
}

func hashFieldElements(values ...*big.Int) *big.Int {
	return hashing.Fields(values...)
}
