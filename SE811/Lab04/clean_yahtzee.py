class Yahtzee:

    def __init__(self, d1, d2, d3, d4, d5):
        self.dice = [d1, d2, d3, d4, d5]


@staticmethod
def _count_dice(dice):
    counts = [0] * 6
    for d in dice:
        counts[d - 1] += 1
    return counts

@staticmethod
def _sum_of_value(dice, value):
    return sum(d for d in dice if d == value)


def ones(self):
    return self._sum_of_value(self.dice, 1)

def twos(self):
    return self._sum_of_value(self.dice, 2)

def threes(self):
    return self._sum_of_value(self.dice, 3)

def fours(self):
    return self._sum_of_value(self.dice, 4)

def fives(self):
    return self._sum_of_value(self.dice, 5)

def sixes(self):
    return self._sum_of_value(self.dice, 6)


def chance(self):
    return sum(self.dice)

def yahtzee(self):
    counts = self._count_dice(self.dice)
    return 50 if 5 in counts else 0

def score_pair(self):
    counts = self._count_dice(self.dice)
    for i in range(5, -1, -1):
        if counts[i] >= 2:
            return (i + 1) * 2
    return 0

def two_pair(self):
    counts = self._count_dice(self.dice)
    pairs = [i + 1 for i in range(6) if counts[i] >= 2]
    if len(pairs) >= 2:
        return sum(pairs[-2:]) * 2
    return 0


def three_of_a_kind(self):
    counts = self._count_dice(self.dice)
    for i in range(6):
        if counts[i] >= 3:
            return (i + 1) * 3
    return 0

def four_of_a_kind(self):
    counts = self._count_dice(self.dice)
    for i in range(6):
        if counts[i] >= 4:
            return (i + 1) * 4
    return 0


def small_straight(self):
    return 15 if sorted(self.dice) == [1, 2, 3, 4, 5] else 0

def large_straight(self):
    return 20 if sorted(self.dice) == [2, 3, 4, 5, 6] else 0


def full_house(self):
    counts = self._count_dice(self.dice)
    has_two = None
    has_three = None

    for i in range(6):
        if counts[i] == 2:
            has_two = i + 1
        elif counts[i] == 3:
            has_three = i + 1

    if has_two and has_three:
        return has_two * 2 + has_three * 3
    return 0

