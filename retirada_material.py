"""Comprovante de retirada com miniaturas, em PDF separado da OS."""
import base64
from html import escape
import os
from pathlib import Path
import shutil
import tempfile

import pymupdf

from branding import CAMINHO_LOGO_GUI, inserir_logo
from dimensoes import formatar_variante

_CSS = """
body {font-family:sans-serif; font-size:8.5pt; color:#222; margin:0;}
h1 {font-size:11pt; color:#173e61; margin:0 0 3pt;}
h2 {font-size:9pt; color:#174d7a; margin:7pt 0 4pt;}
p {line-height:1.25; margin:4pt 0;}
table {border-collapse:collapse; width:100%; font-size:8.5pt;}
td, th {padding:3pt; text-align:left; vertical-align:top; border-bottom:0.6pt solid #dce1e5;}
th {font-size:8pt; color:#174d7a; background:#e6f1fb;}
.dados td {width:245pt; background:#f4f6f8; border:2pt solid white;}
.rotulo {font-size:7pt; color:#66727c;}
.resumo {padding:5pt; background:#e6f1fb; color:#174d7a; margin-top:6pt;}
.declaracao {border:0.7pt solid #adc4d6; padding:8pt; margin-top:10pt;}
.assinaturas td {width:245pt; padding:22pt 6pt 0; border:0; font-size:8pt;}
.linha {border-top:0.7pt solid #666; padding-top:5pt;}
.suave {font-size:8pt; color:#66727c;}
"""


def _texto(valor):
    return escape(str(valor or ""))


def caminho_pdf(pasta_saida, nome_cliente):
    return Path(pasta_saida) / f"RETIRADA - {nome_cliente.upper()}.pdf"


def _miniatura_html(item):
    bruto = item.get("thumbnail_bytes")
    if bruto:
        try:
            pix = pymupdf.Pixmap(bruto)
            largura = 36 * min(1, pix.width / pix.height)
            altura = 36 * min(1, pix.height / pix.width)
            if bruto.startswith(b"\xff\xd8"):
                mime = "image/jpeg"
            else:
                bruto = pix.tobytes("png")
                mime = "image/png"
            codificado = base64.b64encode(bruto).decode("ascii")
            return f'<img src="data:{mime};base64,{codificado}" style="width:{largura}pt;height:{altura}pt">'
        except Exception:
            pass
    return '<div style="background:#eef0f2;color:#66727c;font-size:7pt;padding:5pt">Sem<br>miniatura</div>'


def _linha_item(item, descrever, nome_cliente):
    dimensao = item.get("dimensao")
    medida = (f"{dimensao['largura_m']:.2f} x {dimensao['altura_m']:.2f} m".replace(".", ",")
              if dimensao else "Medida não informada")
    variante = formatar_variante(item["variante"]) if item.get("variante") else ""
    # Material composto identifica a MESMA peça, sem acrescentar unidades.
    material = item["categoria"]
    if item.get("categoria_extra"):
        material += " + " + item["categoria_extra"]
    return (f'<tr><td style="width:44pt">{_miniatura_html(item)}</td>'
            f'<td style="width:276pt"><b>{_texto(material)}</b>'
            f'{" <span class=suave>" + _texto(variante) + "</span>" if variante else ""}'
            f'<br>{_texto(descrever(item["arquivo"], item["categoria"], nome_cliente))}'
            f'</td><td style="width:115pt">{_texto(medida)}</td>'
            f'<td style="width:55pt"><b>{item["quantidade"]} UN</b></td></tr>')


def _cabe_na_folha(html, caixa):
    # Mede com o mesmo renderizador da página final, sem reduzir as fontes
    # e sem sobrepor tentativas bem-sucedidas no documento definitivo.
    with pymupdf.open() as rascunho:
        pagina = rascunho.new_page(width=595.27, height=841.89)
        sobra, _ = pagina.insert_htmlbox(caixa, html, css=_CSS, scale_low=1)
        return sobra >= 0


def montar_comprovante(nome_cliente, nome_gerente, nome_produtor,
                       itens, data_hora_atual, referencia_os, descrever):
    """Monta um PDF próprio, usando os mesmos itens e miniaturas da OS.

    Motorista, data da retirada e assinaturas ficam para preenchimento na
    conferência física. Gerar o documento não registra uma retirada real.
    Declaração, ressalvas e assinaturas aparecem apenas na última folha,
    abrangendo todos os materiais do documento. Os dados do transporte
    ficam na primeira folha; cliente e referência da OS identificam todas.
    """
    pdf_retirada = pymupdf.open()
    total_unidades = sum(item["quantidade"] for item in itens)
    linhas = [_linha_item(item, descrever, nome_cliente) for item in itens]
    indices = []
    inicio = 0
    caixa = pymupdf.Rect(36,68,559,790)
    while inicio < len(itens) or not indices:
        pagina = pdf_retirada.new_page(width=595.27, height=841.89)
        inserir_logo(pagina, pymupdf.Rect(36,22,106,50), caminho=CAMINHO_LOGO_GUI)
        pagina.insert_text((120,36), "COMPROVANTE DE RETIRADA", fontname="hebo", fontsize=12,
                            color=(0.1,0.29,0.45))
        pagina.insert_text((120,50), "LOGÍSTICA · RETIRADA DE MATERIAL", fontsize=7, color=(0.4,0.4,0.4))
        pagina.draw_line((36,61),(559,61), color=(0.7,0.75,0.8), width=0.7)
        cabecalho = f"""
        <h1>{_texto(nome_cliente.upper())}</h1>
        <p class="suave">OS de referência: {_texto(referencia_os)}<br>
        Atualização da OS: {_texto(data_hora_atual)}</p>
        """
        if not indices:
            cabecalho += f"""
        <p class="suave">Gerente: {_texto(nome_gerente)} · Produtor: {_texto(nome_produtor)}</p>
        <table class="dados">
        <tr><td><span class="rotulo">MOTORISTA / TRANSPORTADORA</span><br>________________ / ________________</td>
        <td><span class="rotulo">VEÍCULO / PLACA</span><br>________________ / ________________</td></tr>
        <tr><td><span class="rotulo">DATA E HORA DA RETIRADA</span><br>____/____/________ às ____:____</td>
        <td><span class="rotulo">DESTINO / LOCAL DE ENTREGA</span><br>__________________________________</td></tr>
        </table>
        """
        cabecalho += '<h2>MATERIAIS RETIRADOS</h2>'

        def conteudo(quantidade, ultima):
            fim = inicio + quantidade
            subtotal = sum(item["quantidade"] for item in itens[inicio:fim])
            tabela = ('<table><tr><th>Imagem</th><th>Material / peça</th><th>Medida</th><th>Retirada</th></tr>'
                      + "".join(linhas[inicio:fim]) + "</table>" if itens else
                      '<p>Nenhum material listado na OS.</p>')
            rodape = f"""
            <div class="resumo"><b>Nesta folha: {subtotal} unidades</b> · Total da OS: {total_unidades} unidades</div>
            """ if itens else '<p class="suave">Sem materiais para retirada.</p>'
            if ultima and itens:
                rodape += """
            <div class="declaracao">Declaro que retirei os materiais relacionados em todas as páginas deste documento, nas quantidades
            indicadas, após conferência com o responsável pela liberação, para transporte ao destino informado.
            <p>Ressalvas / avarias: __________________________________________<br>
            ___________________________________________________________</p></div>
            <table class="assinaturas"><tr><td><div class="linha">Motorista: assinatura e nome legível</div></td>
            <td><div class="linha">Responsável pela liberação: assinatura e nome</div></td></tr></table>
            """
            return cabecalho + tabela + rodape

        restantes = len(itens) - inicio
        html = conteudo(restantes, ultima=True)
        if _cabe_na_folha(html, caixa):
            quantidade = restantes
        else:
            # Aproveita a altura real das linhas, sem limite fixo de itens.
            # Guarda ao menos uma peça para a última folha com assinatura.
            baixo, alto, quantidade = 1, restantes - 1, 0
            while baixo <= alto:
                meio = (baixo + alto) // 2
                if _cabe_na_folha(conteudo(meio, ultima=False), caixa):
                    quantidade = meio
                    baixo = meio + 1
                else:
                    alto = meio - 1
            if not quantidade:
                pdf_retirada.close()
                raise ValueError("Não foi possível acomodar o item no comprovante de retirada em A4.")
            html = conteudo(quantidade, ultima=False)
        spare, _ = pagina.insert_htmlbox(caixa, html, css=_CSS, scale_low=1)
        if spare < 0:
            pdf_retirada.close()
            raise ValueError("Não foi possível paginar o comprovante de retirada em A4.")
        indices.append(len(pdf_retirada) - 1)
        inicio += quantidade
    for numero, indice in enumerate(indices, 1):
        pagina = pdf_retirada[indice]
        pagina.draw_line((36,798),(559,798), color=(0.8,0.82,0.84), width=0.5)
        pagina.insert_text((36,814), "UNY CV · Conferir os materiais e preencher na retirada", fontsize=7,
                            color=(0.4,0.4,0.4))
        pagina.insert_textbox(pymupdf.Rect(420,805,559,824), f"Retirada · Página {numero} de {len(indices)}",
                               fontsize=7, align=2, color=(0.4,0.4,0.4))
    return pdf_retirada


def salvar_par_documentos(pdf_os, pdf_retirada, destino_os, destino_retirada):
    """Prepara os dois PDFs antes de publicar; em caso de falha restaura o par.

    Um PDF aberto no Windows pode impedir a troca. Nesse caso, a geração
    falha e as versões anteriores são preservadas para uma nova tentativa.
    """
    temporarios = []
    preparados = []
    publicados = []
    try:
        for documento, destino in ((pdf_os, destino_os), (pdf_retirada, destino_retirada)):
            destino = Path(destino)
            fd, nome = tempfile.mkstemp(prefix=".os_retirada_", suffix=".pdf", dir=destino.parent)
            os.close(fd)
            preparado = Path(nome)
            temporarios.append(preparado)
            documento.save(str(preparado), garbage=4, deflate=True)
            backup = None
            if destino.exists():
                fd, nome = tempfile.mkstemp(prefix=".os_retirada_", suffix=".bak", dir=destino.parent)
                os.close(fd)
                backup = Path(nome)
                temporarios.append(backup)
                shutil.copy2(destino, backup)
            preparados.append((preparado, destino, backup))
        for preparado, destino, backup in preparados:
            os.replace(preparado, destino)
            publicados.append((destino, backup))
    except Exception:
        for destino, backup in reversed(publicados):
            if backup:
                os.replace(backup, destino)
            else:
                destino.unlink(missing_ok=True)
        raise
    finally:
        for caminho in temporarios:
            caminho.unlink(missing_ok=True)
