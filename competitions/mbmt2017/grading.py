"""The official MBMT 2017 grading algorithm.

The following file is intended for use as a modular plugin that
implements various grading functions for the MBMT website. In order
grading functions must be registered to either a round ID and
optionally a question ID.
"""


from django.db.models import Q

import math
import statistics

import grading.models as g
from grading.grading import CompetitionGrader, cached
from grading.models import CORRECT, ESTIMATION


SUBJECT1 = "subject1"
SUBJECT2 = "subject2"
GUTS = "guts"
TEAM = "team"


class Grader(CompetitionGrader):
    """Grader specific to MBMT 2017."""

    COMPETITION = "mbmt2017"

    LAMBDA = 0.52

    cache = {}

    def __init__(self):
        """Initialize the MBMT 2017 grader."""

        super().__init__()
        self.individual_bonus = {}

        # Question graders
        self.register_question_grader(
            Q(round__ref=SUBJECT1),
            self.subject1_question_grader)
        self.register_question_grader(
            Q(round__ref=SUBJECT2),
            self.subject2_question_grader)
        self.register_question_grader(
            Q(type=ESTIMATION),
            self.guts_question_grader)

    def _calculate_individual_bonuses(self, round1, round2):
        """Calculate the point bonuses for an individual round."""

        self.individual_bonus = {}

        factors = {}
        for i, round in enumerate((round1, round2)):
            for question in round.questions.all():
                for answer in g.Answer.objects.filter(question=question).all():

                    # Ignores people whose grading view is not opened
                    division = answer.student.team.division
                    subject = answer.student.subject1 if i == 0 else answer.student.subject2

                    if division not in factors:
                        factors[division] = {}
                        self.individual_bonus[division] = {}
                    if subject not in factors[division]:
                        factors[division][subject] = {}
                        self.individual_bonus[division][subject] = {}
                    if question.id not in factors[division][subject]:
                        factors[division][subject][question.id] = [0, 0]  # Correct, total
                    factors[division][subject][question.id][0] += answer.value or 0
                    factors[division][subject][question.id][1] += 1

        for division in factors:
            for subject in factors[division]:
                for question in factors[division][subject]:
                    correct, total = factors[division][subject][question]
                    self.individual_bonus[division][subject] = (
                        0 if correct == 0 else self.LAMBDA * math.log(total / correct))

    def subject1_question_grader(self, question, answer):
        """Grade an individual question."""

        return (question.weight * (answer.value or 0) *
                self.individual_bonus[answer.student.team.division][answer.student.subject1])

    def subject2_question_grader(self, question, answer):
        """Grade an individual question."""

        return (question.weight * (answer.value or 0) *
                self.individual_bonus[answer.student.team.division][answer.student.subject2])

    def guts_question_grader(self, question: g.Question, answer: g.Answer):
        """Grade a guts question."""

        value = 0
        if question.type == g.QUESTION_TYPES["correct"]:
            value = answer.value
        elif question.type == g.QUESTION_TYPES["estimation"]:
            e = answer.value
            a = question.answer
            if question.number == 26:
                max_below = g.Answer.objects.filter(value__lte=e).exclude(answer).order_by("value").first()
                value = min(12, e - max_below)
            elif question.number == 27:
                value = 12 * 2 ** (-abs(e-a)/60)
            elif question.number == 28:
                value = 0 if e <= 0 else 12 * (16 * math.log10(max(e/a, a/e)) + 1) ** (-0.5)
            elif question.number == 29:
                value = 0 if e <= 0 else 12 * min(e/a, a/e) ** 0.5
            elif question.number == 30:
                value = 0 if e <= 0 else max(0, 12 - 4 * math.log10(max(e/a, a/e)))
        return value * question.weight

    def team_z_round_grader(self, round: g.Round):
        """General team round grader based on Z score."""

        raw_scores = self.grade_round(round)
        for division in raw_scores:
            data = list(map(lambda team: raw_scores[division][team], raw_scores[division]))
            mean = statistics.mean(data)
            dev = statistics.stdev(data, mean)
            for team in raw_scores[division]:
                raw_scores[division][team] = (raw_scores[division][team] - mean) / dev
        return raw_scores

    def team_round_grader(self, round: g.Round):
        """Grader for the team round."""

        return self.team_z_round_grader(round)

    # Cached for use in live grading
    @cached(cache, "guts_scores")
    def guts_round_grader(self, round: g.Round):
        """Grader for the guts round."""

        return self.team_z_round_grader(round)

    @cached(cache, "individual_scores")
    def calculate_individual_scores(self, competition: g.Competition):
        """Custom function that groups both subject rounds together."""

        subject1 = competition.rounds.filter(ref="subject1").first()
        subject2 = competition.rounds.filter(ref="subject2").first()
        self._calculate_individual_bonuses(subject1, subject2)
        raw_scores1 = self.grade_round(subject1)
        raw_scores2 = self.grade_round(subject2)
        final_scores = {}

        # TODO: not silently ignore missing students or divisions
        # This ignores students who received answers for one test but not another
        for division in set(raw_scores1.keys()) & set(raw_scores2.keys()):
            final_scores[division] = {}
            for student in set(raw_scores2[division].keys()) & set(raw_scores2[division].keys()):
                final_scores[division][student] = (raw_scores1[division][student] + raw_scores2[division][student]) / 2

        return final_scores

    @cached(cache, "team_individual_scores")
    def calculate_team_individual_scores(self, competition: g.Competition):
        """Custom function that combines team and guts scores."""

        # Fuck my life

    @cached(cache, "team_scores")
    def calculate_team_scores(self, competition: g.Competition):
        """Calculate the team scores."""

        # Fuck you

    def grade_competition(self, competition: g.Competition):
        """Grade the entire competition."""

        # Why
