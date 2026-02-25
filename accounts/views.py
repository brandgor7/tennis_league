from django.shortcuts import render
from django.contrib.auth.views import LoginView, LogoutView


def design_preview(request):
    """Temporary dev view — shows the full design system with mock data."""
    return render(request, 'design_preview.html')
