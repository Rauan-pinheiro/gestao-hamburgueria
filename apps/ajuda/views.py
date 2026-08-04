from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class LeiaMeView(LoginRequiredMixin, TemplateView):
    template_name = 'ajuda/leiame.html'
