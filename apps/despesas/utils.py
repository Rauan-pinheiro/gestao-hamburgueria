"""Aritmética de datas para recorrência de despesas, sem depender de bibliotecas externas."""
import calendar
from datetime import timedelta


def somar_periodo(data, periodicidade):
    """Retorna `data` avançada de acordo com a periodicidade (SEMANAL, MENSAL ou ANUAL).

    Em meses/anos, se o dia não existir no mês de destino (ex: 31 de um mês de 30 dias,
    ou 29 de fevereiro em ano não bissexto), usa o último dia válido daquele mês.
    """
    if periodicidade == 'SEMANAL':
        return data + timedelta(days=7)

    if periodicidade == 'ANUAL':
        ano = data.year + 1
        ultimo_dia = calendar.monthrange(ano, data.month)[1]
        return data.replace(year=ano, day=min(data.day, ultimo_dia))

    if periodicidade == 'MENSAL':
        mes = data.month + 1
        ano = data.year
        if mes > 12:
            mes = 1
            ano += 1
        ultimo_dia = calendar.monthrange(ano, mes)[1]
        return data.replace(year=ano, month=mes, day=min(data.day, ultimo_dia))

    raise ValueError(f'Periodicidade desconhecida: {periodicidade}')


def primeiro_e_ultimo_dia_mes(data):
    ultimo_dia = calendar.monthrange(data.year, data.month)[1]
    return data.replace(day=1), data.replace(day=ultimo_dia)


def meses_anteriores(data_referencia, quantidade):
    """Lista de `quantidade` tuplas (ano, mes), da mais antiga para a mais recente, terminando no mês de `data_referencia`."""
    meses = []
    ano, mes = data_referencia.year, data_referencia.month
    for _ in range(quantidade):
        meses.append((ano, mes))
        mes -= 1
        if mes == 0:
            mes = 12
            ano -= 1
    return list(reversed(meses))
