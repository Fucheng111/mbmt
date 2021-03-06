from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect, HttpResponse
from django.db.models import Q

import json
import math
import collections
import itertools
import traceback

from home.models import User, Competition
from coaches.models import Coaching, Student, Team, DIVISIONS_MAP, DIVISIONS, SUBJECTS
from .models import Round, Question, Answer, ESTIMATION
from . import grading


# Some quick utility functions

def columnize(objects, columns):
    """Return a list of rows of a column layout."""

    size = int(math.ceil(len(objects) / columns))
    return list(itertools.zip_longest(*[objects[i:i+size] for i in range(0, len(objects), size)]))


# Dashboard utilities and logistics views. We should probably write a
# spreadsheet generator at some point.

@staff_member_required
def index(request):
    return render(request, "grading/index.html", {
        "competition": Competition.current(),
        "coaching": Coaching.current().all()})


@staff_member_required
def students(request):
    return render(request, "grading/student/view.html", {
        "students": Student.current().order_by("name").all()})


@staff_member_required
def teams(request):
    return render(request, "grading/team/view.html", {
        "teams": Team.current().order_by("number").all()})


@staff_member_required
def score(request, grouping, any_id, round_id):
    """Scoring view."""

    competition = Competition.current()
    round = competition.rounds.filter(ref=round_id).first()

    if grouping == "team":
        return score_team(request, any_id, round)
    elif grouping == "individual":
        return score_individual(request, any_id, round)


def score_team(request, team_id, round):
    """Scoring view for a team."""

    # Iterate questions and get answers
    team = Team.objects.filter(id=team_id).first()
    answers = []
    question_answer = []
    for question in round.questions.order_by("number").all():
        answer = Answer.objects.filter(team=team, question=question).first()
        if not answer:
            answer = Answer(team=team, question=question)
            answer.save()
        answers.append(answer)
        question_answer.append((question, answer))

    # Update the answers
    if request.method == "POST":
        update_answers(request, answers)
        return redirect("team_view")

    # Render the grading view
    return render(request, "grading/grader.html", {
        "name": team.name,
        "division": team.get_division_display,
        "round": round,
        "question_answer": question_answer,
        "mode": "team"})


def score_individual(request, student_id, round):
    """Scoring view for an individual."""

    # Iterate questions and get answers
    student = Student.objects.filter(id=student_id).first()
    answers = []
    question_answer = []
    for question in round.questions.order_by("number").all():
        answer = Answer.objects.filter(student=student, question=question).first()
        if not answer:
            answer = Answer(student=student, question=question)
            answer.save()
        answers.append(answer)
        question_answer.append((question, answer))

    # Update the answers
    if request.method == "POST":
        update_answers(request, answers)
        return redirect("student_view")

    # Render the grading view
    return render(request, "grading/grader.html", {
        "name": student.name,
        "division": student.team.get_division_display,
        "round": round,
        "question_answer": question_answer,
        "mode": "student"})


def update_answers(request, answers):
    """Update the answers to a round by an individual or group."""

    for answer in answers:
        id = str(answer.question.id)
        if id in request.POST:
            value = None if str(request.POST[id]) == "" else float(request.POST[id])
            if answer.value != value:
                answer.value = value
                answer.save()


@login_required
@staff_member_required
def shirts(request):
    """Shirt sizes view."""

    teams = Team.current()
    teachers = {}
    totals = collections.Counter()
    for team in teams:
        if team.school.user not in teachers:
            teachers[team.school.user] = [team.school.user, [], collections.Counter()]
        teachers[team.school.user][1].extend(list(team.students.all()))
        for student in team.students.all():
            teachers[team.school.user][2][student.get_size_display()] += 1
            totals[student.get_size_display()] += 1
    for teacher in teachers:
        teachers[teacher][1].sort(key=lambda x: x.name)
    return render(request, "grading/shirts.html", {
        "teachers": list(teachers.values()),
        "totals": totals})


@login_required
@staff_member_required
def attendance(request):
    """Display the attendance page."""

    # If data is posted
    if request.method == "POST":
        attendance_post(request)
        return redirect("attendance")

    # Format students into nice columns
    students = Student.current().all()
    count = request.GET.get("columns", 4)
    columns = columnize(students, count)
    return render(request, "grading/attendance.html", {"students": columns})


def attendance_post(request):
    """Handle post data from the attendance.

    There's some degree of weirdness here, as check boxes don't post
    anything unless they're checked. To prevent this, hidden inputs
    are included for every check box with the absent value. The final
    result is accessed by getting the list of posted values and
    checking if present is in it. To minimize saves, only students
    whose attendance has changed are modified.
    """

    # Iterate post data for numeric entires
    for iid in filter(lambda x: x.isnumeric(), request.POST):
        student = Student.objects.filter(id=iid).first()

        # Check if student, check present or absent
        if student:
            values = request.POST.getlist(iid)
            if "absent" in values:

                # Modify in database
                attending = "present" in request.POST.getlist(iid)
                if student.attending != attending:
                    student.attending = attending
                    student.save()


@staff_member_required
def student_name_tags(request):
    """Display a table from which student name tags can be generated."""

    return render(request, "grading/tags/students.html", {"students": Student.current()})


@staff_member_required
def teacher_name_tags(request):
    """Display a table from which student name tags can be generated."""

    users = User.objects.filter(
        is_staff=False, is_superuser=False, school__isnull=False).order_by("school__name")
    users = list(filter(lambda user: user.school and user.school.teams.count(), users))
    return render(request, "grading/tags/teacher.html", {"teachers": users})


def live(request, round):
    """Get the live guts scoreboard."""

    if round == "guts":
        return render(request, "grading/guts.html")
    else:
        return redirect("student_view")


@staff_member_required
def live_update(request, round):
    """Get the live scoreboard update."""

    if round == "guts":
        grader = Competition.current().grader
        scores = grader.guts_live_round_scores(use_cache_before=20)
        named_scores = dict()
        for division in scores:
            division_name = DIVISIONS_MAP[division]
            named_scores[division_name] = {}
            for team in scores[division]:
                named_scores[division_name][team.name] = scores[division][team]
        return HttpResponse(json.dumps(named_scores).encode())
    else:
        return HttpResponse("{}")


@login_required
def sponsor_scoreboard(request):
    """Get the sponsor scoreboard."""

    grader = Competition.current().grader
    subject_scores = grader.cache_get("subject_scores")
    grader.calculate_team_scores(use_cache=True)
    if subject_scores is None:
        grader.calculate_individual_scores(use_cache=False)

    school = request.user.school
    individual_scores = grading.prepare_school_individual_scores(school, grader.cache_get("subject_scores"))
    team_scores = grading.prepare_school_team_scores(
        school,
        grader.cache_get("raw_guts_scores"),
        grader.cache_get("raw_team_scores"),
        grader.cache_get("team_individual_scores"),
        grader.calculate_team_scores(use_cache=True))

    return render(request, "grading/scoring.html", {
        "individual_scores": individual_scores,
        "team_scores": team_scores})


@staff_member_required
def student_scoreboard(request):
    """Do final scoreboard calculations."""

    grader = Competition.current().grader
    if request.method == "POST" and "recalculate" in request.POST:
        grader.calculate_individual_scores(use_cache=False)
        return redirect("student_scoreboard")

    try:
        individual_scores = grading.prepare_individual_scores(grader.calculate_individual_scores(use_cache=True))
        subject_scores = grading.prepare_subject_scores(grader.cache_get("subject_scores"))
        context = {
            "individual_scores": individual_scores,
            "subject_scores": subject_scores,
            "individual_powers": grader.individual_powers,
            "individual_bonus": grader.individual_bonus}
    except Exception:
        context = {"error": traceback.format_exc().replace("\n", "<br>")}
    return render(request, "grading/student/scoreboard.html", context)


@staff_member_required
def team_scoreboard(request):
    """Show the team scoreboard view."""

    grader = Competition.current().grader
    if request.method == "POST" and "recalculate" in request.POST:
        grader.calculate_team_scores(use_cache=False)
        return redirect("team_scoreboard")

    try:
        team_scores = grader.calculate_team_scores(use_cache=True)
        context = {
            "team_scores": grading.prepare_composite_team_scores(
                grader.cache_get("raw_guts_scores"), grader.cache_get("guts_scores"),
                grader.cache_get("raw_team_scores"), grader.cache_get("team_scores"),
                grader.cache_get("team_individual_scores"),
                team_scores)}
    except Exception:
        context = {"error": traceback.format_exc().replace("\n", "<br>")}
    return render(request, "grading/team/scoreboard.html", context)


@staff_member_required
def statistics(request):
    """View statistics on the last competition."""

    current = Competition.current()
    division_stats = []
    for division, division_name in DIVISIONS:
        stats = []
        subject_stats = []
        for subject, subject_name in SUBJECTS:
            question_stats_dict = {}
            for answer in Answer.objects.filter(
                    Q(student__team__division=division) &
                    Q(question__round__competition=current) &
                    (Q(question__round__ref="subject1") & Q(student__subject1=subject) |
                     Q(question__round__ref="subject2") & Q(student__subject2=subject))):
                if answer.question.number not in question_stats_dict:
                    question_stats_dict[answer.question.number] = [0, 0, 0]
                if answer.value is None:
                    question_stats_dict[answer.question.number][2] += 1
                if answer.value == 1:
                    question_stats_dict[answer.question.number][0] += 1
                elif answer.value == 0:
                    question_stats_dict[answer.question.number][1] += 1
            subject_stats.append((subject_name,) + tuple(question_stats_dict.items()))
        stats.append(list(zip(*subject_stats)))
        for round_ref in ["team", "guts"]:
            question_stats_dict = {}
            estimation_guesses = {}
            for answer in Answer.objects.filter(
                    Q(team__division=division) &
                    Q(question__round__competition=current) & Q(question__round__ref=round_ref)):
                if answer.question.type == ESTIMATION:
                    if answer.question.number not in estimation_guesses:
                        estimation_guesses[answer.question.number] = []
                    estimation_guesses[answer.question.number].append(answer.value)
                    continue
                if answer.question.number not in question_stats_dict:
                    question_stats_dict[answer.question.number] = [0, 0, 0]
                if answer.value is None:
                    question_stats_dict[answer.question.number][2] += 1
                if answer.value == 1:
                    question_stats_dict[answer.question.number][0] += 1
                elif answer.value == 0:
                    question_stats_dict[answer.question.number][1] += 1
            stats.append((round_ref, tuple(question_stats_dict.items())))
            if estimation_guesses:
                stats.append((round_ref + " estimation", tuple(estimation_guesses.items())))
        division_stats.append((division_name, stats))

    return render(request, "grading/statistics.html", {"stats": division_stats, "current": current})
