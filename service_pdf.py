import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from pathlib import Path

def _obter_caminho_pdf_saida():
    docs_path = Path.home() / "Documents" / "RondochassisBot" / "relatorios"
    docs_path.mkdir(parents=True, exist_ok=True)
    return docs_path / "relatorio_pedidos_90_dias.pdf"

def gerar_pdf_relatorio_90_dias(nome_cliente, documento_cliente, pedidos):
    caminho_arquivo = _obter_caminho_pdf_saida()
    
    doc = SimpleDocTemplate(
        str(caminho_arquivo),
        pagesize=letter,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )
    
    elementos = []
    styles = getSampleStyleSheet()
    
    estilo_titulo = ParagraphStyle(
        'TituloRelatorio',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1A365D'),
        alignment=1,
        spaceAfter=6
    )
    
    estilo_subtitulo = ParagraphStyle(
        'SubTituloRelatorio',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#4A5568'),
        alignment=1,
        spaceAfter=15
    )
    
    estilo_cliente = ParagraphStyle(
        'InfoCliente',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.HexColor('#2D3748'),
        spaceAfter=12,
        leading=14
    )
    
    estilo_celula = ParagraphStyle(
        'CelulaTabela',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#2D3748'),
        leading=11
    )
    
    estilo_celula_bold = ParagraphStyle(
        'CelulaTabelaBold',
        parent=estilo_celula,
        fontName='Helvetica-Bold'
    )

    estilo_cabecalho = ParagraphStyle(
        'CabecalhoTabela',
        parent=styles['Normal'],
        fontSize=9,
        fontName='Helvetica-Bold',
        textColor=colors.white,
        alignment=1
    )

    elementos.append(Paragraph("<b>RONDOCHASSIS - RELATÓRIO FINANCEIRO</b>", estilo_titulo))
    elementos.append(Paragraph("Extrato consolidado dos lançamentos dos últimos 90 dias (Aberto e Baixado)", estilo_subtitulo))
    
    info_cliente_texto = f"<b>Cliente:</b> {nome_cliente}<br/><b>CNPJ/CPF:</b> {documento_cliente}"
    elementos.append(Paragraph(info_cliente_texto, estilo_cliente))
    
    dados_tabela = [[
        Paragraph("Data", estilo_cabecalho),
        Paragraph("O.S.", estilo_cabecalho),
        Paragraph("Pedido", estilo_cabecalho),
        Paragraph("Nota", estilo_cabecalho),
        Paragraph("Placa", estilo_cabecalho),
        Paragraph("Valor Total", estilo_cabecalho),
        Paragraph("Parcelas / Vencimento / Status", estilo_cabecalho)
    ]]
    
    total_geral = 0.0

    for ped in pedidos:
        data_ped = ped.get("DATA", "-")
        os_ped = ped.get("OS", "-") or "-"
        pedido_ped = ped.get("PEDIDO", "-") or "-"
        nota_ped = ped.get("NOTA", "-") or "-"
        placa_ped = ped.get("PLACA", "-") or "-"
        valor_tot = ped.get("VALOR_TOTAL", 0.0)
        
        total_geral += valor_tot
        
        detalhes_parcelas = []
        for parc in ped.get("PARCELAS", []):
            p_num = parc.get("PARCELA", 1)
            p_venc = parc.get("VENCIMENTO", "")
            p_val = parc.get("VALOR", 0.0)
            p_status = parc.get("STATUS", "ABERTO")
            
            icone_status = "🟢" if p_status == "BAIXADO" else "🟡"
            detalhes_parcelas.append(f"{icone_status} Parc {p_num}: R$ {p_val:,.2f} | Venc: {p_venc} ({p_status})")
            
        texto_parcelas = "<br/>".join(detalhes_parcelas) if detalhes_parcelas else "N/A"
        
        dados_tabela.append([
            Paragraph(data_ped, estilo_celula),
            Paragraph(os_ped, estilo_celula),
            Paragraph(pedido_ped, estilo_celula),
            Paragraph(nota_ped, estilo_celula),
            Paragraph(placa_ped, estilo_celula),
            Paragraph(f"R$ {valor_tot:,.2f}", estilo_celula_bold),
            Paragraph(texto_parcelas, estilo_celula)
        ])

    dados_tabela.append([
        Paragraph("<b>TOTAL GERAL</b>", estilo_celula_bold),
        Paragraph("", estilo_celula),
        Paragraph("", estilo_celula),
        Paragraph("", estilo_celula),
        Paragraph("", estilo_celula),
        Paragraph(f"<b>R$ {total_geral:,.2f}</b>", estilo_celula_bold),
        Paragraph("", estilo_celula)
    ])

    # Larguras ajustadas com placa mais larga (Total = 552)
    tabela = Table(dados_tabela, colWidths=[60, 40, 45, 40, 65, 75, 227])
    
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1A365D')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#CBD5E0')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EDF2F7')),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
    ]))
    
    elementos.append(tabela)
    
    doc.build(elementos)
    return str(caminho_arquivo)