"""Geração de PDF com os dados de um orçamento da IA preditiva."""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

LARANJA = colors.HexColor('#ffa832')
CINZA = colors.HexColor('#f2f2f2')


def _formatar_moeda(valor) -> str:
    try:
        return f"R$ {float(valor):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except (TypeError, ValueError):
        return str(valor)


def _formatar_percentual(valor) -> str:
    try:
        return f"{float(valor) * 100:.2f}%".replace('.', ',')
    except (TypeError, ValueError):
        return str(valor)


def gerar_pdf_orcamento(orcamento, meses) -> bytes:
    """Monta um PDF em memória com os dados do orçamento e a projeção mensal."""
    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=f"Orçamento #{orcamento.id_orcamento}",
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle(
        'TituloOmni', parent=estilos['Title'], textColor=LARANJA, fontSize=20
    )
    subtitulo = ParagraphStyle(
        'SubtituloOmni', parent=estilos['Heading2'], textColor=colors.black
    )

    veiculo = orcamento.id_veiculo
    descricao_veiculo = (
        f"{veiculo.tipo} {veiculo.modelo}" if veiculo else 'Veículo não informado'
    )

    elementos = [
        Paragraph('OmniFrota - Predição Orçamentária', titulo),
        Spacer(1, 0.5 * cm),
        Paragraph(f'Orçamento #{orcamento.id_orcamento}', subtitulo),
        Spacer(1, 0.3 * cm),
    ]

    resumo = [
        ['Veículo', descricao_veiculo],
        ['Data do orçamento', orcamento.data_orcamento.strftime('%d/%m/%Y')],
        ['Data prevista', orcamento.data_predicao.strftime('%d/%m/%Y')],
        ['Valor total previsto', _formatar_moeda(orcamento.valor)],
        ['Taxa de desvio', _formatar_percentual(orcamento.taxa_desvio)],
        ['Status', orcamento.get_status_display()],
    ]
    tabela_resumo = Table(resumo, colWidths=[6 * cm, 9 * cm])
    tabela_resumo.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), CINZA),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.black),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elementos.append(tabela_resumo)

    previsao = list(orcamento.previsao_mensal or [])
    if previsao:
        elementos.append(Spacer(1, 0.8 * cm))
        elementos.append(Paragraph('Projeção mensal de gastos', subtitulo))
        elementos.append(Spacer(1, 0.3 * cm))

        cabecalho = ['Mês', 'Valor previsto']
        linhas = [cabecalho]
        for indice, valor in enumerate(previsao):
            rotulo = meses[indice] if indice < len(meses) else f'Mês {indice + 1}'
            linhas.append([rotulo, _formatar_moeda(valor)])

        tabela_previsao = Table(linhas, colWidths=[6 * cm, 9 * cm])
        tabela_previsao.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), LARANJA),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CINZA]),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elementos.append(tabela_previsao)

    elementos.append(Spacer(1, 1 * cm))
    elementos.append(Paragraph(
        'Documento gerado automaticamente pelo sistema OmniFrota.',
        estilos['Italic'],
    ))

    documento.build(elementos)
    return buffer.getvalue()
