def configuracao_geral(request):
    if not request.user.is_authenticated:
        return {}
    from .models import ConfiguracaoGeral
    return {'configuracao_geral': ConfiguracaoGeral.get_solo()}
