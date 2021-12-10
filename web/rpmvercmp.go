package main

type Version string
type Tape []rune
type Token int
type Action int

// Lexical symbols
const (
	TILDE     Token = iota // Tilde "~"
	EOT                    // End of tape
	CARRET                 // Carret "^"
	LETTER                 // Alphabet letter [a-zA-Z]
	ZERO                   // Zero "0"
	DIGIT                  // Non-zero digit [1-9]
	SEPARATOR              // Anything else is treated as separator
)

// Recognise lexical symbol under head of the tape
func lex(tape Tape) Token {
	switch {
	case len(tape) == 0:
		return EOT
	case tape[0] == '0':
		return ZERO
	case tape[0] >= '1' && tape[0] <= '9':
		return DIGIT
	case tape[0] >= 'a' && tape[0] <= 'z':
		return LETTER
	case tape[0] >= 'A' && tape[0] <= 'Z':
		return LETTER
	case tape[0] == '~':
		return TILDE
	case tape[0] == '^':
		return CARRET
	default:
		return SEPARATOR
	}
}

// Action to be taken by the Turing machine
const (
	GT0 Action = iota // Go to state 0
	GT1               // Go to state 1
	GT2               // Go to state 2
	GT3               // Go to state 3
	RLT               // Stop; reply "less than" (-1)
	REQ               // Stop; reply "equal to" (0)
	RGT               // Stop; reply "greater than" (+1)
	CMP               // Compare two runes, continue if equal
	NOP               // Do nothing
	ADP               // Advance tape P by one rune
	ADQ               // Advance tape Q by one rune
	APQ               // Advance both tapes by one rune each
)

// Action table for Turing machine.
// Indices are: current state, tokens under head of tape P and Q
var action_table = [4][7][7]Action{
	{
		{APQ, RLT, RLT, RLT, RLT, RLT, ADQ},
		{RGT, REQ, RLT, RLT, RLT, RLT, ADQ},
		{RGT, RGT, APQ, RLT, RLT, RLT, ADQ},
		{RGT, RGT, RGT, GT1, RLT, RLT, ADQ},
		{RGT, RGT, RGT, RGT, GT2, GT2, ADQ},
		{RGT, RGT, RGT, RGT, GT2, GT3, ADQ},
		{ADP, ADP, ADP, ADP, ADP, ADP, APQ},
	}, {
		{GT0, RLT, RLT, RLT, RLT, RLT, GT0},
		{RGT, REQ, RLT, RLT, RLT, RLT, GT0},
		{RGT, RGT, GT0, RLT, RLT, RLT, GT0},
		{RGT, RGT, RGT, CMP, RGT, RGT, RGT},
		{RGT, RGT, RGT, RLT, GT2, GT2, GT0},
		{RGT, RGT, RGT, RLT, GT2, GT3, GT0},
		{GT0, GT0, GT0, RLT, GT0, GT0, GT0},
	}, {
		{GT0, RLT, RLT, RLT, ADQ, RLT, GT0},
		{RGT, REQ, RLT, RLT, ADQ, RLT, GT0},
		{RGT, RGT, GT0, RLT, ADQ, RLT, GT0},
		{RGT, RGT, RGT, GT1, ADQ, RLT, GT0},
		{ADP, ADP, ADP, ADP, APQ, ADP, ADP},
		{RGT, RGT, RGT, RGT, ADQ, GT3, RGT},
		{GT0, GT0, GT0, GT0, ADQ, RLT, GT0},
	}, {
		{GT0, RLT, RLT, RLT, RLT, RLT, GT0},
		{RGT, REQ, RLT, RLT, RLT, RLT, GT0},
		{RGT, RGT, GT0, RLT, RLT, RLT, GT0},
		{RGT, RGT, RGT, GT1, RLT, RLT, GT0},
		{RGT, RGT, RGT, RGT, CMP, CMP, RGT},
		{RGT, RGT, RGT, RGT, CMP, CMP, RGT},
		{GT0, GT0, GT0, GT0, RLT, RLT, GT0},
	},
}

// Compare two RPM version strings. Return -1, 0 or 1.
// Implemented as a Turing machine with two finite tapes P,Q
func (a Version) RpmVerCmp(b Version) int {

	P, Q := Tape(a), Tape(b)
	state := 0

	// Run Turing machine until it decides to stop.
	for {
		tokP, tokQ := lex(P), lex(Q)
		action := action_table[state][tokP][tokQ]
		if action <= GT3 {
			state = int(action)
			action = action_table[state][tokP][tokQ]
		}
		if action <= RGT {
			return int(action - 5)
		}
		if action == CMP && P[0] != Q[0] {
			return int((P[0]-Q[0])>>31 | 1)
		}
		if action&1 != 0 {
			P = P[1:]
		}
		if action&2 != 0 {
			Q = Q[1:]
		}
	}
}
