"""
Camada fina sobre o `pywin32` (win32print) para enviar bytes crus (RAW) a uma
impressora já instalada no Windows — funciona com impressoras USB, de rede ou em
porta compartilhada, porque quem abstrai o transporte é o próprio spooler do Windows,
não este código.

Só é importado de fato (e só precisa do pywin32 instalado) quando o agente roda num
Windows com impressora configurada — isso mantém `formatador.py` livre desta
dependência, para poder ser testado em qualquer sistema operacional sem hardware.
"""
import logging

logger = logging.getLogger('printer_agent')


class ImpressoraError(Exception):
    """Erro pronto para mostrar ao usuário: mensagem em português, sem jargão técnico."""


def _win32print():
    try:
        import win32print
        return win32print
    except ImportError as exc:
        raise ImpressoraError(
            'O módulo "pywin32" não está instalado neste computador. Instale com '
            '"pip install pywin32" e inicie o agente novamente.'
        ) from exc


def listar_impressoras():
    """Nomes exatos das impressoras que o Windows reconhece neste computador."""
    win32print = _win32print()
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    try:
        return [info[2] for info in win32print.EnumPrinters(flags)]
    except Exception as exc:
        logger.exception('Falha ao consultar impressoras instaladas no Windows')
        raise ImpressoraError(
            'Não foi possível consultar as impressoras do Windows. Verifique se o serviço '
            '"Spooler de Impressão" (Print Spooler) está em execução (Serviços do Windows).'
        ) from exc


def imprimir_bytes(nome_impressora, dados_bytes):
    """
    Envia `dados_bytes` (já formatados em ESC/POS, ver formatador.py) como um trabalho
    RAW para a impressora `nome_impressora` — o nome precisa ser exatamente igual ao
    que aparece em "Impressoras e Scanners" do Windows. Levanta `ImpressoraError` com
    mensagem amigável para qualquer falha conhecida (impressora não configurada, não
    encontrada, desligada/desconectada, spooler parado, etc.).
    """
    win32print = _win32print()

    if not nome_impressora:
        raise ImpressoraError(
            'Nenhuma impressora configurada. Abra printer_agent/config.json e defina o '
            'nome exato da impressora térmica no campo "impressora".'
        )

    if nome_impressora not in listar_impressoras():
        raise ImpressoraError(
            f'A impressora "{nome_impressora}" não foi encontrada no Windows. Verifique se '
            'ela está ligada e conectada ao computador, e se o nome em config.json está '
            'exatamente igual ao mostrado em "Impressoras e Scanners".'
        )

    try:
        handle = win32print.OpenPrinter(nome_impressora)
    except Exception as exc:
        logger.exception('Falha ao abrir a impressora "%s"', nome_impressora)
        raise ImpressoraError(
            'Não foi possível imprimir o pedido. Verifique se a impressora térmica está '
            'ligada e conectada ao computador.'
        ) from exc

    try:
        try:
            win32print.StartDocPrinter(handle, 1, ('Pedido - gestao-hamburgueria', None, 'RAW'))
            try:
                win32print.StartPagePrinter(handle)
                win32print.WritePrinter(handle, dados_bytes)
                win32print.EndPagePrinter(handle)
            finally:
                win32print.EndDocPrinter(handle)
        except ImpressoraError:
            raise
        except Exception as exc:
            logger.exception('Falha ao enviar o trabalho de impressão para "%s"', nome_impressora)
            raise ImpressoraError(
                'Não foi possível imprimir o pedido. Verifique se a impressora térmica está '
                'ligada, conectada ao computador e com papel, e tente novamente.'
            ) from exc
    finally:
        win32print.ClosePrinter(handle)
