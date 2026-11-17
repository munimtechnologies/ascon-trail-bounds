# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Made with AI agents working in the name of MV2 of Munim, Inc. (mv2@munimtech.com).
"""ascon_model: an exact SAT (CNF) model of differential characteristics of the
Ascon permutation (NIST SP 800-232), for proving bounds on the number of
differentially active S-boxes.

Pure standard-library Python. This module only BUILDS formulas and CHECKS trails;
solving is done by run_bounds.py with an off-the-shelf SAT solver.

State: five 64-bit rows x0..x4. S-box layer: the 5-bit S-box on every column j
(bit j of x0..x4, x0 is the most significant bit of the S-box index). Linear layer:
x_i ^= (x_i >>> a_i) ^ (x_i >>> b_i). Round constants do not change differences.

A characteristic over R rounds is a list of (x_r, y_r): x_r is the S-box-layer input
difference of round r, y_r its output difference, with DDT[x_r col][y_r col] > 0 for
every column and x_{r+1} = L(y_r). An S-box is active when its column of x_r is nonzero.
"""

__version__ = "0.1.0"

MASK64 = (1 << 64) - 1
ROT = ((19, 28), (61, 39), (1, 6), (10, 17), (7, 41))
ROUND_CONSTANTS = (0xF0, 0xE1, 0xD2, 0xC3, 0xB4, 0xA5,
                   0x96, 0x87, 0x78, 0x69, 0x5A, 0x4B)
# The S-box table as printed in the Ascon specification (index = x0 x1 x2 x3 x4).
SBOX_SPEC = (0x04, 0x0B, 0x1F, 0x14, 0x1A, 0x15, 0x09, 0x02,
             0x1B, 0x05, 0x08, 0x12, 0x1D, 0x03, 0x06, 0x1C,
             0x1E, 0x13, 0x07, 0x0E, 0x00, 0x0D, 0x11, 0x18,
             0x10, 0x0C, 0x01, 0x19, 0x16, 0x0A, 0x0F, 0x17)


# ---------------------------------------------------------------- the permutation
def _sbox_bitsliced(x0, x1, x2, x3, x4, mask):
    """The bitsliced S-box of the Ascon reference implementation."""
    x0 ^= x4
    x4 ^= x3
    x2 ^= x1
    t0 = (~x0 & mask) & x1
    t1 = (~x1 & mask) & x2
    t2 = (~x2 & mask) & x3
    t3 = (~x3 & mask) & x4
    t4 = (~x4 & mask) & x0
    x0 ^= t1
    x1 ^= t2
    x2 ^= t3
    x3 ^= t4
    x4 ^= t0
    x1 ^= x0
    x0 ^= x4
    x3 ^= x2
    x2 = ~x2 & mask
    return x0, x1, x2, x3, x4


def sbox5(v):
    """5-bit S-box on index v (x0 = bit 4 ... x4 = bit 0), via the bitsliced form."""
    bits = [(v >> (4 - i)) & 1 for i in range(5)]
    out = _sbox_bitsliced(*bits, 1)
    return sum(out[i] << (4 - i) for i in range(5))


def rotr(x, s):
    return ((x >> s) | (x << (64 - s))) & MASK64


def linear(words):
    return tuple(w ^ rotr(w, a) ^ rotr(w, b) for w, (a, b) in zip(words, ROT))


def sbox_layer(words):
    return _sbox_bitsliced(*words, MASK64)


def permutation_round(state, rc):
    x0, x1, x2, x3, x4 = state
    return linear(sbox_layer((x0, x1, x2 ^ rc, x3, x4)))


def column(words, j):
    return sum(((words[i] >> j) & 1) << (4 - i) for i in range(5))


def rotate_state(words, s):
    return tuple(rotr(w, s) for w in words)


# ---------------------------------------------------------------- DDT and S-box CNF
_DDT = None


def ddt():
    global _DDT
    if _DDT is None:
        table = [[0] * 32 for _ in range(32)]
        s = [sbox5(v) for v in range(32)]
        for x in range(32):
            for a in range(32):
                table[a][s[x] ^ s[x ^ a]] += 1
        _DDT = table
    return _DDT


def prime_implicants(on_set, nbits):
    """Quine-McCluskey prime implicants of the function whose ON-set is on_set
    (no don't-cares). An implicant is (value, mask): mask bits are free, value has
    zeros at masked positions."""
    current = {(m, 0) for m in on_set}
    primes = set()
    while current:
        merged = set()
        used = set()
        groups = {}
        for v, m in current:
            groups.setdefault(m, set()).add(v)
        for m, vals in groups.items():
            for v in vals:
                for k in range(nbits):
                    bit = 1 << k
                    if (m & bit) or (v & bit):
                        continue
                    if (v | bit) in vals:
                        merged.add((v, m | bit))
                        used.add((v, m))
                        used.add((v | bit, m))
        primes |= current - used
        current = merged
    return primes


def cube_members(value, mask):
    free = [1 << k for k in range(mask.bit_length()) if mask & (1 << k)]
    out = []
    for sub in range(1 << len(free)):
        v = value
        for idx, bit in enumerate(free):
            if sub >> idx & 1:
                v |= bit
        out.append(v)
    return out


def greedy_cover(primes, on_set):
    """Deterministic greedy set cover of on_set by prime implicants."""
    order = sorted(primes)
    members = {p: set(cube_members(*p)) for p in order}
    uncovered = set(on_set)
    chosen = []
    while uncovered:
        best = max(order, key=lambda p: (len(members[p] & uncovered), bin(p[1]).count("1"), p))
        gain = members[best] & uncovered
        if not gain:
            raise RuntimeError("cover failed")
        chosen.append(best)
        uncovered -= gain
    return chosen


_SBOX_CNF = None


def sbox_cnf():
    """CNF over 10 local variables (1..10) that is satisfied exactly by the pairs
    (a, b) with DDT[a][b] > 0. Local variable k+1 is bit k of p = (a << 5) | b."""
    global _SBOX_CNF
    if _SBOX_CNF is None:
        table = ddt()
        impossible = [(a << 5) | b for a in range(32) for b in range(32) if table[a][b] == 0]
        cubes = greedy_cover(prime_implicants(impossible, 10), impossible)
        clauses = []
        for value, mask in cubes:
            clause = []
            for k in range(10):
                if mask >> k & 1:
                    continue
                clause.append(-(k + 1) if value >> k & 1 else (k + 1))
            clauses.append(tuple(clause))
        _SBOX_CNF = tuple(clauses)
    return _SBOX_CNF


def eval_local_sbox_cnf(a, b):
    p = (a << 5) | b
    for clause in sbox_cnf():
        if not any((lit > 0) == bool(p >> (abs(lit) - 1) & 1) for lit in clause):
            return False
    return True


# ---------------------------------------------------------------- the trail model
class TrailModel:
    """Variables and structural clauses for an R-round differential characteristic."""

    def __init__(self, rounds):
        if rounds < 1:
            raise ValueError("rounds >= 1")
        self.rounds = rounds
        self.nv = 0
        self.x = [[[self._new() for _ in range(64)] for _ in range(5)] for _ in range(rounds)]
        self.y = [[[self._new() for _ in range(64)] for _ in range(5)] for _ in range(rounds)]
        self.act = [[self._new() for _ in range(64)] for _ in range(rounds)]
        self.clauses = []
        self._build()

    def _new(self):
        self.nv += 1
        return self.nv

    def _local_to_global(self, r, j, local):
        k = abs(local) - 1
        if k >= 5:      # input-difference bit (k - 5) of a -> row 4 - (k - 5)
            var = self.x[r][4 - (k - 5)][j]
        else:           # output-difference bit k of b -> row 4 - k
            var = self.y[r][4 - k][j]
        return var if local > 0 else -var

    def _build(self):
        local = sbox_cnf()
        for r in range(self.rounds):
            for j in range(64):
                for clause in local:
                    self.clauses.append([self._local_to_global(r, j, lit) for lit in clause])
                a = self.act[r][j]
                xs = [self.x[r][i][j] for i in range(5)]
                for v in xs:
                    self.clauses.append([-v, a])
                self.clauses.append([-a] + xs)
        for r in range(self.rounds - 1):
            for i, (s1, s2) in enumerate(ROT):
                for j in range(64):
                    vs = (self.x[r + 1][i][j], self.y[r][i][j],
                          self.y[r][i][(j + s1) % 64], self.y[r][i][(j + s2) % 64])
                    self.clauses.extend(xor_zero_clauses(vs))

    def active_vars(self):
        return [v for row in self.act for v in row]

    def assignment_from_trail(self, trail):
        """Map a trail [(xwords, ywords), ...] to a {var: bool} assignment."""
        if len(trail) != self.rounds:
            raise ValueError("trail length")
        val = {}
        for r, (xw, yw) in enumerate(trail):
            for i in range(5):
                for j in range(64):
                    val[self.x[r][i][j]] = bool(xw[i] >> j & 1)
                    val[self.y[r][i][j]] = bool(yw[i] >> j & 1)
            for j in range(64):
                val[self.act[r][j]] = column(xw, j) != 0
        return val

    def decode(self, model):
        pos = {lit for lit in model if lit > 0}
        trail = []
        for r in range(self.rounds):
            xw = tuple(sum(1 << j for j in range(64) if self.x[r][i][j] in pos) for i in range(5))
            yw = tuple(sum(1 << j for j in range(64) if self.y[r][i][j] in pos) for i in range(5))
            trail.append((xw, yw))
        return trail


def xor_zero_clauses(vs):
    """Clauses forcing XOR(vs) == 0 (forbid every odd-parity assignment)."""
    out = []
    n = len(vs)
    for bits in range(1 << n):
        if bin(bits).count("1") % 2 == 1:
            out.append([-v if bits >> k & 1 else v for k, v in enumerate(vs)])
    return out


def seq_counter_atmost(lits, k, next_var):
    """Sinz (2005) sequential-counter encoding of sum(lits) <= k.
    Returns (clauses, next free variable)."""
    n = len(lits)
    if k >= n:
        return [], next_var
    if k <= 0:
        return [[-l] for l in lits], next_var
    s = [[0] * (k + 1) for _ in range(n - 1)]
    for i in range(n - 1):
        for j in range(1, k + 1):
            s[i][j] = next_var
            next_var += 1
    x = lits
    cl = [[-x[0], s[0][1]]]
    for j in range(2, k + 1):
        cl.append([-s[0][j]])
    for i in range(1, n - 1):
        cl.append([-x[i], s[i][1]])
        cl.append([-s[i - 1][1], s[i][1]])
        for j in range(2, k + 1):
            cl.append([-x[i], -s[i - 1][j - 1], s[i][j]])
            cl.append([-s[i - 1][j], s[i][j]])
        cl.append([-x[i], -s[i - 1][k]])
    cl.append([-x[n - 1], -s[n - 2][k]])
    return cl, next_var


def symmetry_round(rounds):
    return 1 if rounds >= 2 else 0


def build_cnf(rounds, bound):
    """CNF satisfiable iff an R-round characteristic with 1..bound active S-boxes exists.

    Without loss of generality (rotational symmetry: the S-box layer works column by
    column and the linear layer only rotates rows) the S-box in column 0 of round
    symmetry_round(rounds) is active; this also excludes the all-zero trail.
    Returns (model, clauses, number_of_variables)."""
    m = TrailModel(rounds)
    clauses = [list(c) for c in m.clauses]
    clauses.append([m.act[symmetry_round(rounds)][0]])
    card, nxt = seq_counter_atmost(m.active_vars(), bound, m.nv + 1)
    clauses.extend(card)
    return m, clauses, nxt - 1


def clauses_satisfied(clauses, val):
    for c in clauses:
        if not any(val[abs(l)] == (l > 0) for l in c):
            return False
    return True


# ---------------------------------------------------------------- independent checks
def check_trail(trail):
    """Independent (formula-free) check of a characteristic. Returns per-round
    active-S-box counts; raises ValueError if the trail is not valid."""
    table = ddt()
    counts = []
    for r, (xw, yw) in enumerate(trail):
        n = 0
        for j in range(64):
            a, b = column(xw, j), column(yw, j)
            if table[a][b] == 0:
                raise ValueError("round %d column %d: DDT[%d][%d] = 0" % (r, j, a, b))
            n += a != 0
        counts.append(n)
        if r + 1 < len(trail) and tuple(trail[r + 1][0]) != linear(yw):
            raise ValueError("round %d: x_{r+1} != L(y_r)" % r)
    if not any(counts):
        raise ValueError("all-zero trail")
    return counts


def trail_from_pair(state, delta, rounds, first_round=0):
    """The differences a real pair (state, state ^ delta) follows through `rounds`
    rounds of the permutation, starting at round index first_round of 12."""
    s1 = tuple(state)
    s2 = tuple(a ^ b for a, b in zip(state, delta))
    trail = []
    for r in range(first_round, first_round + rounds):
        rc = ROUND_CONSTANTS[r % 12]
        a1 = (s1[0], s1[1], s1[2] ^ rc, s1[3], s1[4])
        a2 = (s2[0], s2[1], s2[2] ^ rc, s2[3], s2[4])
        b1, b2 = sbox_layer(a1), sbox_layer(a2)
        trail.append((tuple(p ^ q for p, q in zip(a1, a2)), tuple(p ^ q for p, q in zip(b1, b2))))
        s1, s2 = linear(b1), linear(b2)
    return trail


def rotate_trail(trail, s):
    return [(rotate_state(xw, s), rotate_state(yw, s)) for xw, yw in trail]


def trail_to_hex(trail):
    return [{"in": ["%016x" % w for w in xw], "out": ["%016x" % w for w in yw]} for xw, yw in trail]


def write_dimacs(path, clauses, nvars, comment=""):
    import gzip
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "wt") as f:
        if comment:
            for line in comment.splitlines():
                f.write("c %s\n" % line)
        f.write("p cnf %d %d\n" % (nvars, len(clauses)))
        for c in clauses:
            f.write(" ".join(str(l) for l in c) + " 0\n")
