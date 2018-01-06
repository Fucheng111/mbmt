from django.contrib import auth
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404

from . import models, forms

import datetime


def register(request):
    """The registration page for school sponsors."""

    # Assert post and form is valid
    form = forms.RegisterForm()
    if request.method == "POST":
        form = forms.RegisterForm(request.POST)
        if form.is_valid():

            # Create user and school
            user = User.objects.create_user(
                form.cleaned_data["username"],
                email=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
                first_name=form.cleaned_data["name"],
                last_name=form.cleaned_data["last_name"])
            school = models.School(user=user, name=form.cleaned_data["school_name"])
            school.save()

            # Login the user and redirect
            user = auth.authenticate(username=user.get_username(), password=form.cleaned_data["password"])
            auth.login(request, user)
            return redirect("coaches:teams")

    if request.user.is_authenticated:
        return redirect("coaches:teams")

    return render(request, "coaches/register.html", {"form": form, "competition": models.Competition.current()})


@login_required
def display_teams(request):
    """Display current teams."""

    return render(request, "coaches/teams.html", {"allow_edit_teams": allow_edit_teams()})


@login_required
def edit_team(request, pk=None):
    """Add a team to the list."""

    if not allow_edit_teams():
        return redirect("teams")

    team = None
    students = models.Student.objects.none()

    if pk:
        team = get_object_or_404(models.Team, id=pk)
        students = team.students.all()

    team_form = forms.TeamForm(instance=team)
    student_forms = forms.StudentFormSet(queryset=students)

    # Register a team from posted data
    if request.method == "POST":
        team_form = forms.TeamForm(request.POST, instance=team)
        student_forms = forms.StudentFormSet(request.POST, queryset=students)

        # Check validity and create team
        if team_form.is_valid() and student_forms.is_valid():

            # If not editing existing
            if team:
                team.save()
            else:
                team = team_form.save(commit=False)
                team.school = request.user.school
                team.save()

            form_students = student_forms.save(commit=False)
            for student in form_students:
                student.team = team
                student.save()

            return redirect("teams")

    # Render the form view
    return render(request, "coaches/team.html", {
        "team_form": team_form,
        "student_forms": student_forms,
        "student_helper": forms.PrettyHelper()})


@login_required
def remove_team(request, pk=None):
    """Remove the team."""

    if pk:
        models.Team.objects.filter(id=pk).delete()
    return redirect("teams")