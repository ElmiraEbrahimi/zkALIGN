// Package hashing defines the application hash encodings. Do not replace the
// byte framing with reduction of arbitrary 32-byte strings modulo the field.
package hashing

import (
	"encoding/hex"
	"math/big"

	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	"github.com/consensys/gnark-crypto/ecc/bn254/fr/mimc"
)

// Outside the reserved trace/leaf/node range 20260910..20260943.
const ByteDomain = 20261001
const Scheme = "bn254-mimc-gnark-v2"

// Fields matches gnark's BN254 MiMC field-element hashing exactly.
func Fields(values ...*big.Int) *big.Int {
	h := mimc.NewMiMC()
	for _, value := range values {
		var element fr.Element
		element.SetBigInt(value)
		block := element.Bytes()
		_, _ = h.Write(block[:])
	}
	return new(big.Int).SetBytes(h.Sum(nil))
}

// Bytes hashes a domain-separated, injective framing of byte strings. Each
// part's byte length is included and 31-byte big-endian chunks fit in the field
// without reduction. Leading zeroes, part boundaries and trailing zeroes are
// consequently unambiguous. Domain names are themselves the first framed part.
func Bytes(parts ...[]byte) []byte {
	values := []*big.Int{big.NewInt(ByteDomain), big.NewInt(int64(len(parts)))}
	for _, part := range parts {
		values = append(values, new(big.Int).SetUint64(uint64(len(part))))
		for start := 0; start < len(part); start += 31 {
			end := start + 31
			if end > len(part) {
				end = len(part)
			}
			values = append(values, new(big.Int).SetBytes(part[start:end]))
		}
	}
	return Fields(values...).FillBytes(make([]byte, 32))
}

func Hex(parts ...[]byte) string  { return hex.EncodeToString(Bytes(parts...)) }
func Manifest(data []byte) string { return Hex([]byte("zkALIGN:audit:manifest:v2"), data) }
func VerificationKey(data []byte) string {
	return Hex([]byte("zkALIGN:audit:verification-key:v2"), data)
}
func File(data []byte) string { return Hex([]byte("zkALIGN:file:v2"), data) }
