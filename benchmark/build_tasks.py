#!/usr/bin/env python3
# The 59 tasks. Edit here and rerun; tasks.jsonl is generated.
#
# Contract conditions use index expressions, never negative indices or
# negative-step slices (xs[len(xs) - 1], not xs[-1]). CrossHair 0.0.110
# mis-models those and reports counterexamples that do not reproduce
# (Section 6); the swap_ends contract was the one that first hit it. The
# same habit leaked into most of the reference code. Keep new contracts
# that way or the spurious-rate numbers move.
#
# "strategies" overrides the default Hypothesis domains per parameter
# (Appendix B). Descriptions are shown to the models verbatim.
#
# fully_determining (Section 3) is derived, not hand-set: True when some
# postcondition is "__return__ == e" with e not mentioning __return__.
# Pointwise contracts like running_max do not count, even though they also
# pin the result down. 24 of 59 by this rule.
import json
import re
import textwrap

T = []


def is_fully_determining(post):
    for p in post:
        m = re.match(r"^__return__ == (.+)$", p)
        if m and "__return__" not in m.group(1):
            return True
    return False


def task(name, description, signature, pre, post, ref_impl, tests,
         strategies=None, difficulty="easy"):
    d = dict(
        task_id=f"pv_{len(T)+1:03d}",
        name=name,
        description=textwrap.dedent(description).strip(),
        signature=signature.strip(),
        pre=pre,
        post=post,
        ref_impl=textwrap.dedent(ref_impl).strip() + "\n",
        tests=tests,
        difficulty=difficulty,
        fully_determining=is_fully_determining(post),
    )
    if strategies:
        d["strategies"] = strategies
    T.append(d)


task(
    "insert_sorted",
    """Insert value v into the sorted list xs and return a NEW sorted list
    containing all elements of xs plus v. Do not modify xs.""",
    "def insert_sorted(xs: list[int], v: int) -> list[int]:",
    ["xs == sorted(xs)"],
    ["__return__ == sorted(__return__)",
     "len(__return__) == len(xs) + 1",
     "v in __return__"],
    """
    def insert_sorted(xs: list[int], v: int) -> list[int]:
        out = list(xs)
        lo = 0
        while lo < len(out) and out[lo] < v:
            lo += 1
        out.insert(lo, v)
        return out
    """,
    ["assert insert_sorted([1, 3, 5], 4) == [1, 3, 4, 5]",
     "assert insert_sorted([], 7) == [7]",
     "assert insert_sorted([2, 2], 2) == [2, 2, 2]"],
)

task(
    "clamp",
    """Clamp x into the closed interval [lo, hi]: return lo if x < lo,
    hi if x > hi, otherwise x itself.""",
    "def clamp(x: int, lo: int, hi: int) -> int:",
    ["lo <= hi"],
    ["lo <= __return__ <= hi",
     "__return__ in (x, lo, hi)"],
    """
    def clamp(x: int, lo: int, hi: int) -> int:
        if x < lo:
            return lo
        if x > hi:
            return hi
        return x
    """,
    ["assert clamp(5, 0, 10) == 5",
     "assert clamp(-3, 0, 10) == 0",
     "assert clamp(99, 0, 10) == 10"],
)

task(
    "running_max",
    """Return a list r of the same length as xs where r[i] is the maximum
    of xs[0..i] (the running maximum). xs is non-empty.""",
    "def running_max(xs: list[int]) -> list[int]:",
    ["len(xs) >= 1"],
    ["len(__return__) == len(xs)",
     "all(__return__[i] == max(xs[:i+1]) for i in range(len(xs)))"],
    """
    def running_max(xs: list[int]) -> list[int]:
        out = []
        cur = xs[0]
        for v in xs:
            cur = max(cur, v)
            out.append(cur)
        return out
    """,
    ["assert running_max([3, 1, 4, 1, 5]) == [3, 3, 4, 4, 5]",
     "assert running_max([2]) == [2]"],
)

task(
    "remove_duplicates",
    """Return a list with the duplicate elements of xs removed. The result
    must contain exactly the distinct elements of xs (each exactly once).""",
    "def remove_duplicates(xs: list[int]) -> list[int]:",
    [],
    ["len(set(__return__)) == len(__return__)",
     "set(__return__) == set(xs)"],
    """
    def remove_duplicates(xs: list[int]) -> list[int]:
        seen = set()
        out = []
        for v in xs:
            if v not in seen:
                seen.add(v)
                out.append(v)
        return out
    """,
    ["assert remove_duplicates([1, 2, 1, 3]) == [1, 2, 3]",
     "assert remove_duplicates([]) == []"],
)

task(
    "min_and_max",
    """Return a tuple (m, M) with the minimum and maximum element of the
    non-empty list xs.""",
    "def min_and_max(xs: list[int]) -> tuple[int, int]:",
    ["len(xs) >= 1"],
    ["__return__[0] in xs",
     "__return__[1] in xs",
     "all(__return__[0] <= e <= __return__[1] for e in xs)"],
    """
    def min_and_max(xs: list[int]) -> tuple[int, int]:
        m = M = xs[0]
        for v in xs[1:]:
            if v < m:
                m = v
            if v > M:
                M = v
        return (m, M)
    """,
    ["assert min_and_max([3, 1, 2]) == (1, 3)",
     "assert min_and_max([5]) == (5, 5)"],
)

task(
    "count_even",
    """Count how many elements of xs are even.""",
    "def count_even(xs: list[int]) -> int:",
    [],
    ["0 <= __return__ <= len(xs)",
     "__return__ == sum(1 for e in xs if e % 2 == 0)"],
    """
    def count_even(xs: list[int]) -> int:
        c = 0
        for v in xs:
            if v % 2 == 0:
                c += 1
        return c
    """,
    ["assert count_even([1, 2, 3, 4]) == 2",
     "assert count_even([]) == 0"],
)

task(
    "reverse_list",
    """Return a NEW list containing the elements of xs in reverse order.
    Do not modify xs.""",
    "def reverse_list(xs: list[int]) -> list[int]:",
    [],
    ["len(__return__) == len(xs)",
     "all(__return__[i] == xs[len(xs) - 1 - i] for i in range(len(xs)))"],
    """
    def reverse_list(xs: list[int]) -> list[int]:
        return list(reversed(xs))
    """,
    ["assert reverse_list([1, 2, 3]) == [3, 2, 1]",
     "assert reverse_list([]) == []"],
)

task(
    "merge_sorted",
    """Merge two sorted lists a and b into one sorted list containing all
    elements of both (with multiplicity).""",
    "def merge_sorted(a: list[int], b: list[int]) -> list[int]:",
    ["a == sorted(a)", "b == sorted(b)"],
    ["__return__ == sorted(__return__)",
     "len(__return__) == len(a) + len(b)",
     "sorted(__return__) == sorted(a + b)"],
    """
    def merge_sorted(a: list[int], b: list[int]) -> list[int]:
        i = j = 0
        out = []
        while i < len(a) and j < len(b):
            if a[i] <= b[j]:
                out.append(a[i]); i += 1
            else:
                out.append(b[j]); j += 1
        out.extend(a[i:])
        out.extend(b[j:])
        return out
    """,
    ["assert merge_sorted([1, 3], [2, 4]) == [1, 2, 3, 4]",
     "assert merge_sorted([], [1]) == [1]"],
)

task(
    "index_of_value",
    """Return the index of the FIRST occurrence of v in xs. v is guaranteed
    to occur in xs.""",
    "def index_of_value(xs: list[int], v: int) -> int:",
    ["v in xs"],
    ["0 <= __return__ < len(xs)",
     "xs[__return__] == v",
     "v not in xs[:__return__]"],
    """
    def index_of_value(xs: list[int], v: int) -> int:
        for i, e in enumerate(xs):
            if e == v:
                return i
        return -1
    """,
    ["assert index_of_value([5, 3, 5], 5) == 0",
     "assert index_of_value([1, 2, 3], 3) == 2"],
)

task(
    "sum_of_list",
    """Return the sum of all elements of xs (0 for the empty list).""",
    "def sum_of_list(xs: list[int]) -> int:",
    [],
    ["__return__ == sum(xs)"],
    """
    def sum_of_list(xs: list[int]) -> int:
        total = 0
        for v in xs:
            total += v
        return total
    """,
    ["assert sum_of_list([1, 2, 3]) == 6",
     "assert sum_of_list([]) == 0"],
)

task(
    "abs_all",
    """Return a new list where each element is the absolute value of the
    corresponding element of xs.""",
    "def abs_all(xs: list[int]) -> list[int]:",
    [],
    ["__return__ == [abs(e) for e in xs]"],
    """
    def abs_all(xs: list[int]) -> list[int]:
        return [abs(v) for v in xs]
    """,
    ["assert abs_all([-1, 2, -3]) == [1, 2, 3]",
     "assert abs_all([]) == []"],
)

task(
    "is_sorted",
    """Return True iff xs is sorted in non-decreasing order.""",
    "def is_sorted(xs: list[int]) -> bool:",
    [],
    ["__return__ == (xs == sorted(xs))"],
    """
    def is_sorted(xs: list[int]) -> bool:
        return all(xs[i] <= xs[i+1] for i in range(len(xs) - 1))
    """,
    ["assert is_sorted([1, 2, 2, 3]) is True",
     "assert is_sorted([2, 1]) is False",
     "assert is_sorted([]) is True"],
)

task(
    "second_largest",
    """Return the second largest DISTINCT value in xs. xs is guaranteed to
    contain at least two distinct values.""",
    "def second_largest(xs: list[int]) -> int:",
    ["len(set(xs)) >= 2"],
    ["__return__ in xs",
     "__return__ < max(xs)",
     "all(e <= __return__ or e == max(xs) for e in xs)"],
    """
    def second_largest(xs: list[int]) -> int:
        distinct = sorted(set(xs))
        return distinct[-2]
    """,
    ["assert second_largest([1, 3, 2]) == 2",
     "assert second_largest([5, 5, 4]) == 4"],
)

task(
    "split_parity",
    """Split xs into (evens, odds): a tuple of two lists, the first with all
    even elements, the second with all odd elements, each preserving the
    original relative order.""",
    "def split_parity(xs: list[int]) -> tuple[list[int], list[int]]:",
    [],
    ["all(e % 2 == 0 for e in __return__[0])",
     "all(e % 2 != 0 for e in __return__[1])",
     "len(__return__[0]) + len(__return__[1]) == len(xs)",
     "sorted(__return__[0] + __return__[1]) == sorted(xs)"],
    """
    def split_parity(xs: list[int]) -> tuple[list[int], list[int]]:
        evens = [v for v in xs if v % 2 == 0]
        odds = [v for v in xs if v % 2 != 0]
        return (evens, odds)
    """,
    ["assert split_parity([1, 2, 3, 4]) == ([2, 4], [1, 3])",
     "assert split_parity([]) == ([], [])"],
)

task(
    "count_char",
    """Count the number of occurrences of character c in string s.
    c is a single character.""",
    "def count_char(s: str, c: str) -> int:",
    ["len(c) == 1"],
    ["0 <= __return__ <= len(s)",
     "__return__ == s.count(c)"],
    """
    def count_char(s: str, c: str) -> int:
        n = 0
        for ch in s:
            if ch == c:
                n += 1
        return n
    """,
    ["assert count_char('banana', 'a') == 3",
     "assert count_char('', 'x') == 0"],
)

task(
    "repeat_string",
    """Return the string s repeated n times (empty string when n == 0).
    n is between 0 and 5 inclusive.""",
    "def repeat_string(s: str, n: int) -> str:",
    ["0 <= n <= 5"],
    ["len(__return__) == len(s) * n",
     "__return__ == s * n"],
    """
    def repeat_string(s: str, n: int) -> str:
        out = ''
        for _ in range(n):
            out += s
        return out
    """,
    ["assert repeat_string('ab', 3) == 'ababab'",
     "assert repeat_string('x', 0) == ''"],
)

task(
    "unique_sorted",
    """Return the distinct elements of xs in increasing order.""",
    "def unique_sorted(xs: list[int]) -> list[int]:",
    [],
    ["__return__ == sorted(set(xs))"],
    """
    def unique_sorted(xs: list[int]) -> list[int]:
        return sorted(set(xs))
    """,
    ["assert unique_sorted([3, 1, 3, 2]) == [1, 2, 3]",
     "assert unique_sorted([]) == []"],
)

task(
    "interval_contains",
    """Return True iff x lies in the closed interval [lo, hi].""",
    "def interval_contains(lo: int, hi: int, x: int) -> bool:",
    ["lo <= hi"],
    ["__return__ == (lo <= x <= hi)"],
    """
    def interval_contains(lo: int, hi: int, x: int) -> bool:
        return lo <= x <= hi
    """,
    ["assert interval_contains(0, 10, 5) is True",
     "assert interval_contains(0, 10, 11) is False"],
)

task(
    "pairwise_sums",
    """Given two lists a and b of equal length, return the element-wise sum
    list r with r[i] = a[i] + b[i].""",
    "def pairwise_sums(a: list[int], b: list[int]) -> list[int]:",
    ["len(a) == len(b)"],
    ["len(__return__) == len(a)",
     "all(__return__[i] == a[i] + b[i] for i in range(len(a)))"],
    """
    def pairwise_sums(a: list[int], b: list[int]) -> list[int]:
        return [x + y for x, y in zip(a, b)]
    """,
    ["assert pairwise_sums([1, 2], [3, 4]) == [4, 6]",
     "assert pairwise_sums([], []) == []"],
)

task(
    "drop_smaller_than",
    """Return the elements of xs that are greater than or equal to
    threshold t, preserving order.""",
    "def drop_smaller_than(xs: list[int], t: int) -> list[int]:",
    [],
    ["all(e >= t for e in __return__)",
     "len(__return__) == sum(1 for e in xs if e >= t)",
     "all(e in xs for e in __return__)"],
    """
    def drop_smaller_than(xs: list[int], t: int) -> list[int]:
        return [v for v in xs if v >= t]
    """,
    ["assert drop_smaller_than([1, 5, 2, 8], 3) == [5, 8]",
     "assert drop_smaller_than([], 0) == []"],
)

# the contract that first triggered the slice-modeling bug; rewritten with
# index expressions (see top of file)
task(
    "swap_ends",
    """Return a NEW list equal to xs but with the first and last elements
    swapped. xs is non-empty. Do not modify xs.""",
    "def swap_ends(xs: list[int]) -> list[int]:",
    ["len(xs) >= 1"],
    ["len(__return__) == len(xs)",
     "__return__[0] == xs[len(xs) - 1]",
     "__return__[len(xs) - 1] == xs[0]",
     "all(__return__[i] == xs[i] for i in range(1, len(xs) - 1))"],
    """
    def swap_ends(xs: list[int]) -> list[int]:
        out = list(xs)
        out[0], out[-1] = out[-1], out[0]
        return out
    """,
    ["assert swap_ends([1, 2, 3]) == [3, 2, 1]",
     "assert swap_ends([7]) == [7]"],
)


task(
    "rotate_left",
    """Rotate the list xs to the left by k positions and return the result
    as a NEW list. k is between 0 and len(xs) inclusive.""",
    "def rotate_left(xs: list[int], k: int) -> list[int]:",
    ["0 <= k <= len(xs)"],
    ["len(__return__) == len(xs)",
     "all(__return__[i] == xs[(i + k) % len(xs)] for i in range(len(xs)))"],
    """
    def rotate_left(xs: list[int], k: int) -> list[int]:
        return xs[k:] + xs[:k]
    """,
    ["assert rotate_left([1, 2, 3, 4], 1) == [2, 3, 4, 1]",
     "assert rotate_left([1, 2], 0) == [1, 2]",
     "assert rotate_left([], 0) == []"],
    difficulty="medium",
)

task(
    "lower_bound",
    """Return the smallest index r such that all elements before r are
    strictly less than v and all elements from r on are >= v (the insertion
    point of v in the sorted list xs, before any equal elements).""",
    "def lower_bound(xs: list[int], v: int) -> int:",
    ["xs == sorted(xs)"],
    ["0 <= __return__ <= len(xs)",
     "all(xs[i] < v for i in range(__return__))",
     "all(xs[i] >= v for i in range(__return__, len(xs)))"],
    """
    def lower_bound(xs: list[int], v: int) -> int:
        lo, hi = 0, len(xs)
        while lo < hi:
            mid = (lo + hi) // 2
            if xs[mid] < v:
                lo = mid + 1
            else:
                hi = mid
        return lo
    """,
    ["assert lower_bound([1, 2, 2, 3], 2) == 1",
     "assert lower_bound([1, 3], 2) == 1",
     "assert lower_bound([], 5) == 0"],
    difficulty="medium",
)

task(
    "kth_smallest",
    """Return the k-th smallest element of xs, counting duplicates
    (1-indexed: k=1 gives the minimum).""",
    "def kth_smallest(xs: list[int], k: int) -> int:",
    ["1 <= k <= len(xs)"],
    ["__return__ in xs",
     "sum(1 for e in xs if e < __return__) < k",
     "sum(1 for e in xs if e <= __return__) >= k"],
    """
    def kth_smallest(xs: list[int], k: int) -> int:
        return sorted(xs)[k - 1]
    """,
    ["assert kth_smallest([3, 1, 2], 1) == 1",
     "assert kth_smallest([5, 5, 1], 2) == 5",
     "assert kth_smallest([7], 1) == 7"],
    difficulty="medium",
)

task(
    "max_subarray_sum",
    """Return the maximum sum of any non-empty contiguous subarray of the
    non-empty list xs.""",
    "def max_subarray_sum(xs: list[int]) -> int:",
    ["len(xs) >= 1"],
    ["any(__return__ == sum(xs[i:j]) for i in range(len(xs)) for j in range(i + 1, len(xs) + 1))",
     "all(__return__ >= sum(xs[i:j]) for i in range(len(xs)) for j in range(i + 1, len(xs) + 1))"],
    """
    def max_subarray_sum(xs: list[int]) -> int:
        best = cur = xs[0]
        for v in xs[1:]:
            cur = max(v, cur + v)
            best = max(best, cur)
        return best
    """,
    ["assert max_subarray_sum([-2, 1, -3, 4, -1, 2, 1, -5, 4]) == 6",
     "assert max_subarray_sum([-1, -2]) == -1",
     "assert max_subarray_sum([5]) == 5"],
    difficulty="hard",
)

task(
    "move_zeros",
    """Return a new list with all non-zero elements of xs first (in their
    original order) followed by all the zeros.""",
    "def move_zeros(xs: list[int]) -> list[int]:",
    [],
    ["__return__ == [e for e in xs if e != 0] + [0] * xs.count(0)"],
    """
    def move_zeros(xs: list[int]) -> list[int]:
        out = [v for v in xs if v != 0]
        out.extend([0] * xs.count(0))
        return out
    """,
    ["assert move_zeros([0, 1, 0, 3]) == [1, 3, 0, 0]",
     "assert move_zeros([]) == []"],
    difficulty="medium",
)

task(
    "dedupe_adjacent",
    """Collapse runs of equal adjacent elements of xs to a single element,
    preserving order (e.g. [1,1,2,1] -> [1,2,1]).""",
    "def dedupe_adjacent(xs: list[int]) -> list[int]:",
    [],
    ["__return__ == [xs[i] for i in range(len(xs)) if i == 0 or xs[i] != xs[i - 1]]"],
    """
    def dedupe_adjacent(xs: list[int]) -> list[int]:
        out = []
        for v in xs:
            if not out or out[len(out) - 1] != v:
                out.append(v)
        return out
    """,
    ["assert dedupe_adjacent([1, 1, 2, 1]) == [1, 2, 1]",
     "assert dedupe_adjacent([]) == []"],
    difficulty="medium",
)

task(
    "missing_number",
    """xs contains distinct integers, each between 0 and len(xs) inclusive;
    exactly one value in that range is missing. Return the missing value.""",
    "def missing_number(xs: list[int]) -> int:",
    ["len(set(xs)) == len(xs)",
     "all(0 <= e <= len(xs) for e in xs)"],
    ["0 <= __return__ <= len(xs)",
     "__return__ not in xs"],
    """
    def missing_number(xs: list[int]) -> int:
        n = len(xs)
        return n * (n + 1) // 2 - sum(xs)
    """,
    ["assert missing_number([3, 0, 1]) == 2",
     "assert missing_number([0]) == 1",
     "assert missing_number([1]) == 0",
     "assert missing_number([]) == 0"],
    difficulty="medium",
)

task(
    "running_sum",
    """Return the prefix sums of xs: r[i] is the sum of xs[0..i].""",
    "def running_sum(xs: list[int]) -> list[int]:",
    [],
    ["len(__return__) == len(xs)",
     "all(__return__[i] == sum(xs[:i + 1]) for i in range(len(xs)))"],
    """
    def running_sum(xs: list[int]) -> list[int]:
        out = []
        total = 0
        for v in xs:
            total += v
            out.append(total)
        return out
    """,
    ["assert running_sum([1, 2, 3]) == [1, 3, 6]",
     "assert running_sum([]) == []"],
    difficulty="medium",
)

task(
    "argmax_first",
    """Return the index of the FIRST occurrence of the maximum element of
    the non-empty list xs.""",
    "def argmax_first(xs: list[int]) -> int:",
    ["len(xs) >= 1"],
    ["0 <= __return__ < len(xs)",
     "xs[__return__] == max(xs)",
     "all(xs[i] < xs[__return__] for i in range(__return__))"],
    """
    def argmax_first(xs: list[int]) -> int:
        best = 0
        for i in range(1, len(xs)):
            if xs[i] > xs[best]:
                best = i
        return best
    """,
    ["assert argmax_first([1, 3, 3, 2]) == 1",
     "assert argmax_first([5]) == 0"],
    difficulty="medium",
)

task(
    "clamp_all",
    """Clamp every element of xs into the closed interval [lo, hi] and
    return the resulting list.""",
    "def clamp_all(xs: list[int], lo: int, hi: int) -> list[int]:",
    ["lo <= hi"],
    ["__return__ == [min(hi, max(lo, e)) for e in xs]"],
    """
    def clamp_all(xs: list[int], lo: int, hi: int) -> list[int]:
        out = []
        for v in xs:
            if v < lo:
                out.append(lo)
            elif v > hi:
                out.append(hi)
            else:
                out.append(v)
        return out
    """,
    ["assert clamp_all([-5, 0, 5], -1, 3) == [-1, 0, 3]",
     "assert clamp_all([], 0, 1) == []"],
    difficulty="medium",
)

task(
    "chunk_sums",
    """Split xs into consecutive chunks of size k (the last chunk may be
    shorter) and return the list of chunk sums.""",
    "def chunk_sums(xs: list[int], k: int) -> list[int]:",
    ["k >= 1"],
    ["len(__return__) == (len(xs) + k - 1) // k",
     "all(__return__[i] == sum(xs[i * k:(i + 1) * k]) for i in range(len(__return__)))"],
    """
    def chunk_sums(xs: list[int], k: int) -> list[int]:
        out = []
        for i in range(0, len(xs), k):
            out.append(sum(xs[i:i + k]))
        return out
    """,
    ["assert chunk_sums([1, 2, 3, 4, 5], 2) == [3, 7, 5]",
     "assert chunk_sums([], 3) == []"],
    difficulty="medium",
)

task(
    "repeat_each",
    """Return a list where each element of xs is repeated k times in place
    (e.g. [1,2] with k=2 -> [1,1,2,2]). k is between 0 and 4.""",
    "def repeat_each(xs: list[int], k: int) -> list[int]:",
    ["0 <= k <= 4"],
    ["len(__return__) == len(xs) * k",
     "all(__return__[i] == xs[i // k] for i in range(len(xs) * k))"],
    """
    def repeat_each(xs: list[int], k: int) -> list[int]:
        out = []
        for v in xs:
            for _ in range(k):
                out.append(v)
        return out
    """,
    ["assert repeat_each([1, 2], 2) == [1, 1, 2, 2]",
     "assert repeat_each([1], 0) == []"],
    difficulty="medium",
)

task(
    "interleave",
    """Interleave two equal-length lists: return [a[0], b[0], a[1], b[1], ...].""",
    "def interleave(a: list[int], b: list[int]) -> list[int]:",
    ["len(a) == len(b)"],
    ["len(__return__) == 2 * len(a)",
     "all(__return__[2 * i] == a[i] and __return__[2 * i + 1] == b[i] for i in range(len(a)))"],
    """
    def interleave(a: list[int], b: list[int]) -> list[int]:
        out = []
        for x, y in zip(a, b):
            out.append(x)
            out.append(y)
        return out
    """,
    ["assert interleave([1, 3], [2, 4]) == [1, 2, 3, 4]",
     "assert interleave([], []) == []"],
    difficulty="medium",
)

task(
    "two_sum_indices",
    """Return a pair of indices (i, j) with i < j such that
    xs[i] + xs[j] == target. Such a pair is guaranteed to exist.""",
    "def two_sum_indices(xs: list[int], target: int) -> tuple[int, int]:",
    ["any(xs[i] + xs[j] == target for i in range(len(xs)) for j in range(i + 1, len(xs)))"],
    ["0 <= __return__[0] < __return__[1] < len(xs)",
     "xs[__return__[0]] + xs[__return__[1]] == target"],
    """
    def two_sum_indices(xs: list[int], target: int) -> tuple[int, int]:
        for i in range(len(xs)):
            for j in range(i + 1, len(xs)):
                if xs[i] + xs[j] == target:
                    return (i, j)
        return (0, 0)
    """,
    ["assert two_sum_indices([2, 7, 11], 9) == (0, 1)",
     "assert two_sum_indices([3, 3], 6) == (0, 1)"],
    difficulty="hard",
)

task(
    "count_inversions",
    """Count the pairs (i, j) with i < j and xs[i] > xs[j].""",
    "def count_inversions(xs: list[int]) -> int:",
    [],
    ["__return__ == sum(1 for i in range(len(xs)) for j in range(i + 1, len(xs)) if xs[i] > xs[j])"],
    """
    def count_inversions(xs: list[int]) -> int:
        c = 0
        for i in range(len(xs)):
            for j in range(i + 1, len(xs)):
                if xs[i] > xs[j]:
                    c += 1
        return c
    """,
    ["assert count_inversions([2, 1]) == 1",
     "assert count_inversions([1, 2, 3]) == 0",
     "assert count_inversions([3, 2, 1]) == 3"],
    difficulty="medium",
)

task(
    "sum_digits",
    """Return the sum of the decimal digits of the non-negative integer n.""",
    "def sum_digits(n: int) -> int:",
    ["0 <= n <= 1000000"],
    ["__return__ == sum(int(d) for d in str(n))"],
    """
    def sum_digits(n: int) -> int:
        total = 0
        while n > 0:
            total += n % 10
            n //= 10
        return total
    """,
    ["assert sum_digits(123) == 6",
     "assert sum_digits(0) == 0"],
    strategies={"n": "st.integers(min_value=0, max_value=1000000)"},
    difficulty="medium",
)

task(
    "int_to_binary",
    """Return the binary representation of n (0 <= n <= 1024) as a string
    of '0'/'1' characters, without leading zeros ('0' for n == 0).""",
    "def int_to_binary(n: int) -> str:",
    ["0 <= n <= 1024"],
    ["all(c in '01' for c in __return__)",
     "int(__return__, 2) == n",
     "__return__ == '0' or not __return__.startswith('0')"],
    """
    def int_to_binary(n: int) -> str:
        if n == 0:
            return '0'
        out = ''
        while n > 0:
            out = str(n % 2) + out
            n //= 2
        return out
    """,
    ["assert int_to_binary(5) == '101'",
     "assert int_to_binary(0) == '0'"],
    strategies={"n": "st.integers(min_value=0, max_value=1024)"},
    difficulty="medium",
)

task(
    "is_anagram",
    """Return True iff strings a and b are anagrams of each other
    (same characters with the same multiplicities).""",
    "def is_anagram(a: str, b: str) -> bool:",
    [],
    ["__return__ == (sorted(a) == sorted(b))"],
    """
    def is_anagram(a: str, b: str) -> bool:
        if len(a) != len(b):
            return False
        counts = {}
        for c in a:
            counts[c] = counts.get(c, 0) + 1
        for c in b:
            counts[c] = counts.get(c, 0) - 1
        return all(v == 0 for v in counts.values())
    """,
    ["assert is_anagram('listen', 'silent') is True",
     "assert is_anagram('ab', 'aab') is False",
     "assert is_anagram('', '') is True"],
    difficulty="medium",
)

task(
    "caesar_shift",
    """Shift every lowercase letter of s forward by k positions in the
    alphabet, wrapping around from 'z' to 'a'. s contains only lowercase
    letters a-z; 0 <= k <= 25.""",
    "def caesar_shift(s: str, k: int) -> str:",
    ["0 <= k <= 25",
     "all('a' <= c <= 'z' for c in s)"],
    ["len(__return__) == len(s)",
     "all(ord(__return__[i]) == (ord(s[i]) - 97 + k) % 26 + 97 for i in range(len(s)))"],
    """
    def caesar_shift(s: str, k: int) -> str:
        out = []
        for c in s:
            out.append(chr((ord(c) - ord('a') + k) % 26 + ord('a')))
        return ''.join(out)
    """,
    ["assert caesar_shift('abc', 1) == 'bcd'",
     "assert caesar_shift('xyz', 3) == 'abc'",
     "assert caesar_shift('', 5) == ''"],
    strategies={"s": "st.text(alphabet='abcdefghijklmnopqrstuvwxyz', max_size=8)"},
    difficulty="medium",
)

task(
    "strip_vowels",
    """Remove all vowels (a, e, i, o, u) from s and return the rest,
    preserving order.""",
    "def strip_vowels(s: str) -> str:",
    [],
    ["__return__ == ''.join(c for c in s if c not in 'aeiou')"],
    """
    def strip_vowels(s: str) -> str:
        out = ''
        for c in s:
            if c not in 'aeiou':
                out += c
        return out
    """,
    ["assert strip_vowels('banana') == 'bnn'",
     "assert strip_vowels('xyz') == 'xyz'"],
    strategies={"s": "st.text(alphabet='aeioubcdxyz', max_size=8)"},
    difficulty="easy",
)

task(
    "balanced_parens",
    """s consists only of '(' and ')'. Return True iff the parentheses are
    balanced: every prefix has at least as many '(' as ')', and the totals
    are equal.""",
    "def balanced_parens(s: str) -> bool:",
    ["all(c in '()' for c in s)"],
    ["__return__ == (s.count('(') == s.count(')') and "
     "all(s[:i + 1].count(')') <= s[:i + 1].count('(') for i in range(len(s))))"],
    """
    def balanced_parens(s: str) -> bool:
        depth = 0
        for c in s:
            if c == '(':
                depth += 1
            else:
                depth -= 1
            if depth < 0:
                return False
        return depth == 0
    """,
    ["assert balanced_parens('(())') is True",
     "assert balanced_parens(')(') is False",
     "assert balanced_parens('(') is False",
     "assert balanced_parens('') is True"],
    strategies={"s": "st.text(alphabet='()', max_size=10)"},
    difficulty="hard",
)

task(
    "longest_common_prefix",
    """Return the longest common prefix of strings a and b.""",
    "def longest_common_prefix(a: str, b: str) -> str:",
    [],
    ["a.startswith(__return__)",
     "b.startswith(__return__)",
     "len(__return__) == min(len(a), len(b)) or a[len(__return__)] != b[len(__return__)]"],
    """
    def longest_common_prefix(a: str, b: str) -> str:
        i = 0
        while i < len(a) and i < len(b) and a[i] == b[i]:
            i += 1
        return a[:i]
    """,
    ["assert longest_common_prefix('flower', 'flow') == 'flow'",
     "assert longest_common_prefix('dog', 'cat') == ''"],
    difficulty="hard",
)

task(
    "sorted_squares",
    """Given a sorted list xs, return the squares of its elements in
    non-decreasing order.""",
    "def sorted_squares(xs: list[int]) -> list[int]:",
    ["xs == sorted(xs)"],
    ["__return__ == sorted(e * e for e in xs)"],
    """
    def sorted_squares(xs: list[int]) -> list[int]:
        return sorted(v * v for v in xs)
    """,
    ["assert sorted_squares([-3, -1, 2]) == [1, 4, 9]",
     "assert sorted_squares([]) == []"],
    difficulty="medium",
)


task(
    "rle_encode",
    """Run-length encode the string s: return a list of (char, count) pairs
    such that no two adjacent pairs have the same char, every count is >= 1,
    and expanding the pairs reproduces s exactly.""",
    "def rle_encode(s: str) -> list[tuple[str, int]]:",
    [],
    ["all(__return__[i][1] >= 1 for i in range(len(__return__)))",
     "all(__return__[i][0] != __return__[i + 1][0] for i in range(len(__return__) - 1))",
     "''.join(p[0] * p[1] for p in __return__) == s"],
    """
    def rle_encode(s: str) -> list[tuple[str, int]]:
        out = []
        for c in s:
            if out and out[len(out) - 1][0] == c:
                out[len(out) - 1] = (c, out[len(out) - 1][1] + 1)
            else:
                out.append((c, 1))
        return out
    """,
    ["assert rle_encode('aabccc') == [('a', 2), ('b', 1), ('c', 3)]",
     "assert rle_encode('') == []"],
    strategies={"s": "st.text(alphabet='ab', max_size=8)"},
    difficulty="hard",
)

task(
    "longest_run",
    """Return the length of the longest run of equal consecutive characters
    in s (0 for the empty string).""",
    "def longest_run(s: str) -> int:",
    [],
    ["(len(s) == 0 and __return__ == 0) or any(i + __return__ <= len(s) and "
     "all(s[k] == s[i] for k in range(i, i + __return__)) for i in range(len(s)))",
     "all(not (i + __return__ + 1 <= len(s) and "
     "all(s[k] == s[i] for k in range(i, i + __return__ + 1))) for i in range(len(s)))"],
    """
    def longest_run(s: str) -> int:
        best = cur = 0
        prev = None
        for c in s:
            cur = cur + 1 if c == prev else 1
            prev = c
            if cur > best:
                best = cur
        return best
    """,
    ["assert longest_run('aabbba') == 3",
     "assert longest_run('') == 0",
     "assert longest_run('abc') == 1"],
    strategies={"s": "st.text(alphabet='ab', max_size=8)"},
    difficulty="hard",
)

task(
    "first_missing_positive",
    """Return the smallest positive integer (>= 1) that does not occur in xs.""",
    "def first_missing_positive(xs: list[int]) -> int:",
    [],
    ["__return__ >= 1",
     "__return__ not in xs",
     "all(k in xs for k in range(1, __return__))"],
    """
    def first_missing_positive(xs: list[int]) -> int:
        present = set(xs)
        k = 1
        while k in present:
            k += 1
        return k
    """,
    ["assert first_missing_positive([1, 2, 4]) == 3",
     "assert first_missing_positive([-1, 5]) == 1",
     "assert first_missing_positive([]) == 1"],
    difficulty="medium",
)

task(
    "count_pairs_with_sum",
    """Count the index pairs (i, j) with i < j and xs[i] + xs[j] == t.""",
    "def count_pairs_with_sum(xs: list[int], t: int) -> int:",
    [],
    ["__return__ == sum(1 for i in range(len(xs)) for j in range(i + 1, len(xs)) if xs[i] + xs[j] == t)"],
    """
    def count_pairs_with_sum(xs: list[int], t: int) -> int:
        c = 0
        for i in range(len(xs)):
            for j in range(i + 1, len(xs)):
                if xs[i] + xs[j] == t:
                    c += 1
        return c
    """,
    ["assert count_pairs_with_sum([1, 2, 3, 4], 5) == 2",
     "assert count_pairs_with_sum([], 0) == 0"],
    difficulty="medium",
)

task(
    "pivot_partition",
    """Partition xs around pivot p: return (smaller, equal, greater) where
    smaller has all elements < p, equal all elements == p, greater all
    elements > p, and together they contain exactly the elements of xs.""",
    "def pivot_partition(xs: list[int], p: int) -> tuple[list[int], list[int], list[int]]:",
    [],
    ["all(e < p for e in __return__[0])",
     "all(e == p for e in __return__[1])",
     "all(e > p for e in __return__[2])",
     "sorted(__return__[0] + __return__[1] + __return__[2]) == sorted(xs)"],
    """
    def pivot_partition(xs: list[int], p: int) -> tuple[list[int], list[int], list[int]]:
        smaller = [e for e in xs if e < p]
        equal = [e for e in xs if e == p]
        greater = [e for e in xs if e > p]
        return (smaller, equal, greater)
    """,
    ["assert pivot_partition([3, 1, 3, 5], 3) == ([1], [3, 3], [5])",
     "assert pivot_partition([], 0) == ([], [], [])"],
    difficulty="medium",
)

task(
    "mode_smallest",
    """Return the most frequent value in the non-empty list xs; break ties
    by returning the smallest such value.""",
    "def mode_smallest(xs: list[int]) -> int:",
    ["len(xs) >= 1"],
    ["__return__ in xs",
     "all(xs.count(e) <= xs.count(__return__) for e in xs)",
     "all(e >= __return__ for e in xs if xs.count(e) == xs.count(__return__))"],
    """
    def mode_smallest(xs: list[int]) -> int:
        best = xs[0]
        for v in xs:
            cv, cb = xs.count(v), xs.count(best)
            if cv > cb or (cv == cb and v < best):
                best = v
        return best
    """,
    ["assert mode_smallest([1, 2, 2, 3]) == 2",
     "assert mode_smallest([3, 1]) == 1",
     "assert mode_smallest([5]) == 5"],
    difficulty="hard",
)

task(
    "add_big_digits",
    """a and b are non-negative integers represented as little-endian digit
    lists (a[0] is the least significant digit; no leading zeros except for
    the single-digit number 0). Return their sum in the same representation.""",
    "def add_big_digits(a: list[int], b: list[int]) -> list[int]:",
    ["len(a) >= 1", "len(b) >= 1",
     "all(0 <= d <= 9 for d in a)", "all(0 <= d <= 9 for d in b)",
     "a[len(a) - 1] != 0 or len(a) == 1",
     "b[len(b) - 1] != 0 or len(b) == 1"],
    ["all(0 <= d <= 9 for d in __return__)",
     "sum(d * 10 ** i for i, d in enumerate(__return__)) == "
     "sum(d * 10 ** i for i, d in enumerate(a)) + sum(d * 10 ** i for i, d in enumerate(b))",
     "__return__[len(__return__) - 1] != 0 or len(__return__) == 1"],
    """
    def add_big_digits(a: list[int], b: list[int]) -> list[int]:
        out = []
        carry = 0
        for i in range(max(len(a), len(b))):
            s = carry
            if i < len(a):
                s += a[i]
            if i < len(b):
                s += b[i]
            out.append(s % 10)
            carry = s // 10
        if carry:
            out.append(carry)
        while len(out) > 1 and out[len(out) - 1] == 0:
            out.pop()
        return out
    """,
    ["assert add_big_digits([9, 9], [1]) == [0, 0, 1]",
     "assert add_big_digits([0], [0]) == [0]",
     "assert add_big_digits([5], [7]) == [2, 1]"],
    strategies={"a": "st.lists(st.integers(min_value=0, max_value=9), min_size=1, max_size=4)",
                "b": "st.lists(st.integers(min_value=0, max_value=9), min_size=1, max_size=4)"},
    difficulty="hard",
)

task(
    "sort_colors",
    """xs contains only the values 0, 1 and 2. Return the elements sorted in
    non-decreasing order (Dutch national flag).""",
    "def sort_colors(xs: list[int]) -> list[int]:",
    ["all(e in (0, 1, 2) for e in xs)"],
    ["__return__ == sorted(xs)"],
    """
    def sort_colors(xs: list[int]) -> list[int]:
        counts = [0, 0, 0]
        for v in xs:
            counts[v] += 1
        return [0] * counts[0] + [1] * counts[1] + [2] * counts[2]
    """,
    ["assert sort_colors([2, 0, 1, 2]) == [0, 1, 2, 2]",
     "assert sort_colors([]) == []"],
    strategies={"xs": "st.lists(st.integers(min_value=0, max_value=2), max_size=8)"},
    difficulty="medium",
)

task(
    "best_gain",
    """prices is a non-empty list. Return the maximum of prices[j] - prices[i]
    over all pairs with i <= j (0 if prices never rises).""",
    "def best_gain(prices: list[int]) -> int:",
    ["len(prices) >= 1"],
    ["__return__ == max(prices[j] - prices[i] for i in range(len(prices)) for j in range(i, len(prices)))"],
    """
    def best_gain(prices: list[int]) -> int:
        best = 0
        lo = prices[0]
        for p in prices:
            if p - lo > best:
                best = p - lo
            if p < lo:
                lo = p
        return best
    """,
    ["assert best_gain([7, 1, 5, 3, 6, 4]) == 5",
     "assert best_gain([7, 6, 4, 3, 1]) == 0",
     "assert best_gain([5]) == 0"],
    difficulty="hard",
)

task(
    "merge_intervals",
    """iv is a list of closed integer intervals (lo, hi) with lo <= hi,
    sorted by lo. Merge all overlapping or touching intervals and return the
    resulting disjoint intervals sorted by lo.""",
    "def merge_intervals(iv: list[tuple[int, int]]) -> list[tuple[int, int]]:",
    ["all(p[0] <= p[1] for p in iv)",
     "all(iv[i][0] <= iv[i + 1][0] for i in range(len(iv) - 1))"],
    ["all(p[0] <= p[1] for p in __return__)",
     "all(__return__[i][1] < __return__[i + 1][0] for i in range(len(__return__) - 1))",
     "all((any(p[0] <= x <= p[1] for p in iv)) == (any(p[0] <= x <= p[1] for p in __return__)) for x in range(-12, 13))"],
    """
    def merge_intervals(iv: list[tuple[int, int]]) -> list[tuple[int, int]]:
        out = []
        for lo, hi in iv:
            if out and lo <= out[len(out) - 1][1]:
                plo, phi = out[len(out) - 1]
                out[len(out) - 1] = (plo, max(phi, hi))
            else:
                out.append((lo, hi))
        return out
    """,
    ["assert merge_intervals([(1, 3), (2, 6), (8, 10)]) == [(1, 6), (8, 10)]",
     "assert merge_intervals([]) == []",
     "assert merge_intervals([(1, 4), (4, 5)]) == [(1, 5)]"],
    strategies={"iv": "st.lists(st.tuples(st.integers(min_value=-8, max_value=8), st.integers(min_value=0, max_value=6)), max_size=4).map(lambda ps: sorted((a, a + w) for a, w in ps))"},
    difficulty="hard",
)

task(
    "gcd_bounded",
    """Return the greatest common divisor of a and b (both between 1 and 60).""",
    "def gcd_bounded(a: int, b: int) -> int:",
    ["1 <= a <= 60", "1 <= b <= 60"],
    ["__return__ >= 1",
     "a % __return__ == 0",
     "b % __return__ == 0",
     "all(a % d != 0 or b % d != 0 for d in range(__return__ + 1, min(a, b) + 1))"],
    """
    def gcd_bounded(a: int, b: int) -> int:
        while b:
            a, b = b, a % b
        return a
    """,
    ["assert gcd_bounded(12, 18) == 6",
     "assert gcd_bounded(7, 13) == 1",
     "assert gcd_bounded(5, 5) == 5"],
    strategies={"a": "st.integers(min_value=1, max_value=60)",
                "b": "st.integers(min_value=1, max_value=60)"},
    difficulty="hard",
)

task(
    "fibonacci_at",
    """Return the n-th Fibonacci number with F(0) = 0, F(1) = 1.
    n is between 0 and 15.""",
    "def fibonacci_at(n: int) -> int:",
    ["0 <= n <= 15"],
    ["__return__ == (0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610)[n]"],
    """
    def fibonacci_at(n: int) -> int:
        a, b = 0, 1
        for _ in range(n):
            a, b = b, a + b
        return a
    """,
    ["assert fibonacci_at(0) == 0",
     "assert fibonacci_at(1) == 1",
     "assert fibonacci_at(10) == 55"],
    strategies={"n": "st.integers(min_value=0, max_value=15)"},
    difficulty="medium",
)

task(
    "is_rotation",
    """Return True iff string b is a rotation of string a (b can be obtained
    by moving some prefix of a to its end). Every string is a rotation of
    itself; the empty string is a rotation only of the empty string.""",
    "def is_rotation(a: str, b: str) -> bool:",
    [],
    ["__return__ == (len(a) == len(b) and (len(a) == 0 or any(a[i:] + a[:i] == b for i in range(len(a)))))"],
    """
    def is_rotation(a: str, b: str) -> bool:
        if len(a) != len(b):
            return False
        if len(a) == 0:
            return True
        return b in (a + a)
    """,
    ["assert is_rotation('abcde', 'cdeab') is True",
     "assert is_rotation('abc', 'acb') is False",
     "assert is_rotation('', '') is True"],
    strategies={"a": "st.text(alphabet='ab', max_size=6)",
                "b": "st.text(alphabet='ab', max_size=6)"},
    difficulty="hard",
)

task(
    "power_of_two_flag",
    """Return True iff n is a power of two (1, 2, 4, 8, ...).
    n is between 0 and 1024.""",
    "def power_of_two_flag(n: int) -> bool:",
    ["0 <= n <= 1024"],
    ["__return__ == (n in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024))"],
    """
    def power_of_two_flag(n: int) -> bool:
        if n < 1:
            return False
        while n % 2 == 0:
            n //= 2
        return n == 1
    """,
    ["assert power_of_two_flag(8) is True",
     "assert power_of_two_flag(0) is False",
     "assert power_of_two_flag(6) is False",
     "assert power_of_two_flag(1) is True"],
    strategies={"n": "st.integers(min_value=0, max_value=1024)"},
    difficulty="medium",
)

# the parenthetical in this description is clumsy, but it is what every
# logged run saw, so it stays
task(
    "word_lengths",
    """s is a space-separated sentence with no leading/trailing spaces and no
    double spaces. Return the list of word lengths ([] is impossible: the
    empty string yields [] as specified below).""",
    "def word_lengths(s: str) -> list[int]:",
    ["'  ' not in s",
     "not s.startswith(' ')",
     "not s.endswith(' ')"],
    ["__return__ == ([] if s == '' else [len(w) for w in s.split(' ')])"],
    """
    def word_lengths(s: str) -> list[int]:
        if s == '':
            return []
        return [len(w) for w in s.split(' ')]
    """,
    ["assert word_lengths('ab c abc') == [2, 1, 3]",
     "assert word_lengths('') == []",
     "assert word_lengths('a') == [1]"],
    strategies={"s": "st.text(alphabet='ab ', max_size=8)"},
    difficulty="medium",
)


def main():
    with open("tasks.jsonl", "w") as f:
        for t in T:
            f.write(json.dumps(t) + "\n")
    print(f"wrote {len(T)} tasks")


if __name__ == "__main__":
    main()
