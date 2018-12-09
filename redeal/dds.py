# vim: set fileencoding=utf-8
from __future__ import division, print_function
# for pypy compatibility we do not use unicode_literals in this module
from ctypes import *
import json
import os
import sys
import warnings

from .global_defs import *


def to_c_strain(strain):
    return {Strain.C: 3, Strain.D: 2, Strain.H: 1, Strain.S: 0, Strain.N: 4}[strain]


def to_suit(suit):
    return {3: Suit.C, 2: Suit.D, 1: Suit.H, 0: Suit.S}[suit]


def convert_rank(rank):
    return rank.value if isinstance(rank, Rank) else Rank(rank)


class Deal(Structure):
    """The deal struct.
    """

    _fields_ = [("trump", c_int), # 0=S, 1=H, 2=D, 3=C, 4=NT
                ("first", c_int), # leader: 0=N, 1=E, 2=S, 3=W
                ("currentTrickSuit", c_int * 3),
                ("currentTrickRank", c_int * 3), # 2-14, up to 3 cards; 0=unplayed
                # remainCards[hand][suit] is a bit-array (2->2^2, ..., A->2^14)
                ("remainCards", c_uint * 4 * 4)]

    @classmethod
    def from_deal(cls, deal, strain, leader):
        self = cls(trump=to_c_strain(strain),
                   first=leader.value,
                   currentTrickSuit=(c_int * 3)(0, 0, 0),
                   currentTrickRank=(c_int * 3)(0, 0, 0))
        # bit #i (2 ≤ i ≤ 14) is set if card of rank i (A = 14) is held
        for seat, hand in enumerate(deal):
            for suit, holding in enumerate(hand):
                self.remainCards[seat][suit] = sum(
                    1 << convert_rank(rank) for rank in holding)
        return self


class DealPBN(Structure):
    """The dealPBN struct.
    """

    _fields_ = [("trump", c_int), # 0=S, 1=H, 2=D, 3=C, 4=NT
                ("first", c_int), # leader: 0=N, 1=E, 2=S, 3=W
                ("currentTrickSuit", c_int * 3),
                ("currentTrickRank", c_int * 3), # 2-14, up to 3 cards; 0=unplayed
                ("remainCards", c_char * 80)] # PBN-like format

    @classmethod
    def from_deal(cls, deal, strain, leader):
        return cls(trump=to_c_strain(strain),
                   first=leader.value,
                   currentTrickSuit=(c_int * 3)(0, 0, 0),
                   currentTrickRank=(c_int * 3)(0, 0, 0),
                   remainCards=b"N:" + " ".join(
                       ".".join(str(holding) for holding in hand)
                       for hand in deal).encode("ascii"))


class FutureTricks(Structure):
    """The futureTricks struct.
    """

    _fields_ = [("nodes", c_int),
                ("cards", c_int),
                ("suit", c_int * 13),
                ("rank", c_int * 13),
                ("equals", c_int * 13),
                ("score", c_int * 13)]


SolveBoardStatus = {
    1: "No fault",
    -1: "Unknown fault",
    -2: "Zero cards",
    -3: "Target > tricks left",
    -4: "Duplicated cards",
    -5: "Target < -1",
    -7: "Target > 13",
    -8: "Solutions < 1",
    -9: "Solutions > 3",
    -10: "> 52 cards",
    -12: "Invalid deal.currentTrick{Suit,Rank}",
    -13: "Card played in current trick is also remaining",
    -14: "Wrong number of remaining cards in a hand",
    -15: "threadIndex < 0 or >=noOfThreads, noOfThreads is the configured "
         "maximum number of threads"}


def _solve_board(deal, strain, leader, target, sol, mode):
    c_deal = Deal.from_deal(deal, strain, leader)
    futp = FutureTricks()
    status = dll.SolveBoard(c_deal, target, sol, mode, byref(futp), 0)
    if status != 1:
        raise Exception("SolveBoard({}, ...) failed with status {} ({}).".
                        format(deal, status, SolveBoardStatus[status]))
    return futp


def calc_tables(deal):
    hands_pbn = "N:{} {} {} {}".format(deal.north._pbn_str(), deal.east._pbn_str(), deal.south._pbn_str(), deal.west._pbn_str())
    json_in = json.dumps({'pbn': hands_pbn}).encode('ascii')
    ptr = dll.JsonApi_CalcAllTables(json_in)
    json_out = c_char_p(ptr).value.decode("utf-8")
    dll.JsonApi_FreeCPtr(ptr)
    return json.loads(json_out)


def solve(deal, strain, declarer):
    """Return the number of tricks for declarer; wraps SolveBoard.
    """
    leader = Seat[declarer] + 1
    # find one optimal card with its score, even if only one card
    futp = _solve_board(deal, Strain[strain], leader, -1, 1, 1)
    best_score = len(Rank) - futp.score[0]
    return best_score


def solve_pbn(deal, strain, declarer):
    """Return the number of tricks for declarer; wraps SolveBoardPBN.
    """
    leader = Seat[declarer] + 1
    c_deal_pbn = DealPBN.from_deal(deal, Strain[strain], leader)
    status = dll.SolveBoardPBN(c_deal_pbn, -1, 1, 1, byref(futp), 0)
    if status != 1:
        raise Exception("SolveBoardPBN({}, ...) failed with status {} ({}).".
                        format(deal, status, SolveBoardStatus[status]))
    best_score = len(Rank) - futp.score[0]
    return best_score


def valid_cards(deal, strain, leader):
    """Return all cards that can be played.
    """
    futp = _solve_board(deal, Strain[strain], Seat[leader], 0, 2, 1)
    return [Card(to_suit(futp.suit[i]), convert_rank(futp.rank[i]))
            for i in range(futp.cards)]


def solve_all(deal, strain, leader):
    """Return the number of tricks for declarer for each lead; wraps SolveBoard.
    """
    futp = _solve_board(deal, Strain[strain], Seat[leader], -1, 3, 1)
    return {Card(to_suit(futp.suit[i]), convert_rank(futp.rank[i])):
            futp.score[i] for i in range(futp.cards)}


dll_name = DLL = None
if os.name == "posix":
    dll_name = "libdds.so"
    DLL = CDLL
elif os.name == "nt":
    if sys.maxsize > 2 ** 32: # 64-bit Windows
        if sys.version_info >= (3, 5):
            dll_name = "dds-64.dll"
        else:
            warnings.warn("For Windows 64-bit, DDS requires Python>=3.5.")
    else:
        dll_name = "dds-32.dll"
    DLL = WinDLL

if dll_name:
    dll_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            dll_name)

if dll_name and os.path.exists(dll_path):
    dll = DLL(dll_path)
    dll.SolveBoard.argtypes = [
        Deal, c_int, c_int, c_int, POINTER(FutureTricks), c_int]
    dll.SolveBoardPBN.argtypes = [
        DealPBN, c_int, c_int, c_int, POINTER(FutureTricks), c_int]
    dll.JsonApi_CalcAllTables.argtypes = [c_char_p]
    dll.JsonApi_CalcAllTables.restype = c_void_p
    dll.JsonApi_FreeCPtr.argtypes = [c_void_p]
    dll.JsonApi_FreeCPtr.restype = None
   
    if os.name == "posix":
        dll.SetMaxThreads(0)
else:
    def solve(deal, strain, declarer):
        raise Exception("Unable to load DDS.  `solve` is unavailable.")

    def valid_cards(deal, strain, leader):
        raise Exception("Unable to load DDS.  `valid_cards` is unavailable.")

    def solve_all(deal, strain, declarer):
        raise Exception("Unable to load DDS.  `solve_all` is unavailable.")

    def calc_tables(deal):
        raise Exception("Unable to load DDS.  `calc_tables` is unavailable.")
