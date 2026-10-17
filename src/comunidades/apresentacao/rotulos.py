"""Os textos fixos do que vai para a rádio (PDF do roteiro, e-mail, página de confirmação) e do comprovante,
em português, inglês e espanhol (Fase K). Só rótulos: os nomes de comunidade, município e pessoa nunca são
traduzidos. Quem chama escolhe o idioma (o do aviso); sem o idioma, vale o português.
"""

PADRAO = "pt-BR"
HTML_LANG = {"pt-BR": "pt-BR", "en": "en", "es": "es"}

TEXTOS = {
    "pt-BR": {
        "slogan": "O aviso certo, para a comunidade certa",
        "aviso_ficticio": ("Rede elétrica e clientes fictícios nesta demonstração; território, endereços e "
                           "comunidades reais (IBGE, Censo 2022)."),
        "roteiro_rodape": "Norte - roteiro para a rádio - página {pagina}",
        "roteiro_titulo": "Roteiro para a rádio",
        "roteiro_pdf_titulo": "Roteiro para a rádio - {municipio}/{uf} - {data}",
        "roteiro_sub": "{municipio}/{uf} - desligamento programado em {data}, das {horario} - {empresa}",
        "texto_leitura": "Texto para leitura",
        "palavras": "{palavras} palavras - cerca de {segundos} s no ar",
        "inteiras": "Comunidades inteiras", "parciais": "Parte da comunidade", "vizinhas": "Localidades vizinhas (citadas em conjunto)",
        "prazo": "Prazo", "antecedencia": "Antecedência mínima: {prazo}.",
        "vital": "Unidades com equipamento vital: {sim}", "vital_a_confirmar": " ({n} a confirmar)", "vital_fim": " (só a contagem).",
        "aviso_n": " - aviso nº {id}",
        "pdf_gerado": "PDF gerado em {quando} por {quem}. Código do texto (SHA-256): {codigo}.",
        "quando": "{d:%d/%m/%Y} às {d:%H:%M}",
        "solicitado": "Solicitado por {nome} ({perfil}) em {quando} · código de verificação {codigo}",
        "email_assunto": "Aviso de desligamento programado: {municipio}/{uf}, {data} ({codigo})",
        "email_intro": "{empresa}: aviso de desligamento programado para leitura no ar.",
        "email_municipio": "Município", "email_data": "Data", "email_das": "das", "email_codigo": "Código de verificação",
        "email_anexos": "O roteiro (PDF) vai anexo.", "email_anexos_mp3": "O roteiro (PDF) e o áudio (MP3) vão anexos.",
        "email_confirme": "Confirme o recebimento neste link (vale 7 dias, uma vez):",
        "email_botao": "Confirmar recebimento", "email_link_vale": "O link vale 7 dias e uma vez.",
        "conf_titulo": "Confirmar o recebimento", "conf_texto": "{radio}: aviso de desligamento programado de {municipio}, dia {data}, das {horario}.",
        "conf_botao": "Confirmar recebimento", "conf_ja": "Recebimento já confirmado",
        "conf_ja_texto": "O recebimento do aviso de {municipio} já foi confirmado. Obrigado.",
        "conf_ok": "Recebimento confirmado", "conf_ok_texto": "Obrigado, {radio}. A distribuidora já sabe que o aviso chegou.",
        "conf_invalido": "Link inválido", "conf_invalido_texto": "Este link de confirmação não existe.",
        "conf_vencido": "Link vencido", "conf_vencido_texto": "Este link venceu (vale 7 dias). Fale com a distribuidora.",
        "conf_nao": "Não confirmado", "conf_nao_texto": "O link não vale mais (já usado, vencido ou inexistente).",
        "conf_origem": "Pedido de outra origem.",
        "horas": "horas", "dias_uteis": "dias úteis",
    },
    "en": {
        "slogan": "The right notice, for the right community",
        "aviso_ficticio": ("Fictitious power grid and customers in this demonstration; real territory, addresses and "
                           "communities (IBGE, 2022 Census)."),
        "roteiro_rodape": "Norte - script for the radio station - page {pagina}",
        "roteiro_titulo": "Radio script",
        "roteiro_pdf_titulo": "Radio script - {municipio}/{uf} - {data}",
        "roteiro_sub": "{municipio}/{uf} - scheduled power outage on {data}, from {horario} - {empresa}",
        "texto_leitura": "Text to read on air",
        "palavras": "{palavras} words - about {segundos} s on air",
        "inteiras": "Whole communities", "parciais": "Part of the community", "vizinhas": "Nearby areas (mentioned together)",
        "prazo": "Notice period", "antecedencia": "Minimum notice: {prazo}.",
        "vital": "Units with life-support equipment: {sim}", "vital_a_confirmar": " ({n} to be confirmed)", "vital_fim": " (count only).",
        "aviso_n": " - notice no. {id}",
        "pdf_gerado": "PDF generated on {quando} by {quem}. Text code (SHA-256): {codigo}.",
        "quando": "{d:%m/%d/%Y} at {d:%H:%M}",
        "solicitado": "Requested by {nome} ({perfil}) on {quando} · verification code {codigo}",
        "email_assunto": "Scheduled power outage notice: {municipio}/{uf}, {data} ({codigo})",
        "email_intro": "{empresa}: scheduled power outage notice to be read on air.",
        "email_municipio": "Municipality", "email_data": "Date", "email_das": "from", "email_codigo": "Verification code",
        "email_anexos": "The script (PDF) is attached.", "email_anexos_mp3": "The script (PDF) and the audio (MP3) are attached.",
        "email_confirme": "Please confirm receipt at this link (valid for 7 days, once):",
        "email_botao": "Confirm receipt", "email_link_vale": "The link is valid for 7 days and can be used once.",
        "conf_titulo": "Confirm receipt", "conf_texto": "{radio}: scheduled power outage notice for {municipio}, on {data}, from {horario}.",
        "conf_botao": "Confirm receipt", "conf_ja": "Receipt already confirmed",
        "conf_ja_texto": "Receipt of the notice for {municipio} has already been confirmed. Thank you.",
        "conf_ok": "Receipt confirmed", "conf_ok_texto": "Thank you, {radio}. The utility now knows the notice arrived.",
        "conf_invalido": "Invalid link", "conf_invalido_texto": "This confirmation link does not exist.",
        "conf_vencido": "Expired link", "conf_vencido_texto": "This link has expired (it is valid for 7 days). Please contact the utility.",
        "conf_nao": "Not confirmed", "conf_nao_texto": "The link is no longer valid (already used, expired or nonexistent).",
        "conf_origem": "Request from another origin.",
        "horas": "hours", "dias_uteis": "business days",
    },
    "es": {
        "slogan": "El aviso correcto, para la comunidad correcta",
        "aviso_ficticio": ("Red eléctrica y clientes ficticios en esta demostración; territorio, direcciones y "
                           "comunidades reales (IBGE, Censo 2022)."),
        "roteiro_rodape": "Norte - guion para la radio - página {pagina}",
        "roteiro_titulo": "Guion para la radio",
        "roteiro_pdf_titulo": "Guion para la radio - {municipio}/{uf} - {data}",
        "roteiro_sub": "{municipio}/{uf} - corte programado el {data}, de {horario} - {empresa}",
        "texto_leitura": "Texto para leer al aire",
        "palavras": "{palavras} palabras - unos {segundos} s al aire",
        "inteiras": "Comunidades enteras", "parciais": "Parte de la comunidad", "vizinhas": "Localidades vecinas (citadas en conjunto)",
        "prazo": "Plazo", "antecedencia": "Antelación mínima: {prazo}.",
        "vital": "Unidades con equipos de soporte vital: {sim}", "vital_a_confirmar": " ({n} por confirmar)", "vital_fim": " (solo el número).",
        "aviso_n": " - aviso n.º {id}",
        "pdf_gerado": "PDF generado el {quando} por {quem}. Código del texto (SHA-256): {codigo}.",
        "quando": "{d:%d/%m/%Y} a las {d:%H:%M}",
        "solicitado": "Solicitado por {nome} ({perfil}) el {quando} · código de verificación {codigo}",
        "email_assunto": "Aviso de corte programado: {municipio}/{uf}, {data} ({codigo})",
        "email_intro": "{empresa}: aviso de corte programado para leer al aire.",
        "email_municipio": "Municipio", "email_data": "Fecha", "email_das": "de", "email_codigo": "Código de verificación",
        "email_anexos": "El guion (PDF) va adjunto.", "email_anexos_mp3": "El guion (PDF) y el audio (MP3) van adjuntos.",
        "email_confirme": "Confirme la recepción en este enlace (válido 7 días, una sola vez):",
        "email_botao": "Confirmar recepción", "email_link_vale": "El enlace es válido 7 días y una sola vez.",
        "conf_titulo": "Confirmar la recepción", "conf_texto": "{radio}: aviso de corte programado de {municipio}, el {data}, de {horario}.",
        "conf_botao": "Confirmar recepción", "conf_ja": "Recepción ya confirmada",
        "conf_ja_texto": "La recepción del aviso de {municipio} ya fue confirmada. Gracias.",
        "conf_ok": "Recepción confirmada", "conf_ok_texto": "Gracias, {radio}. La distribuidora ya sabe que el aviso llegó.",
        "conf_invalido": "Enlace inválido", "conf_invalido_texto": "Este enlace de confirmación no existe.",
        "conf_vencido": "Enlace vencido", "conf_vencido_texto": "Este enlace venció (es válido 7 días). Hable con la distribuidora.",
        "conf_nao": "No confirmado", "conf_nao_texto": "El enlace ya no es válido (ya usado, vencido o inexistente).",
        "conf_origem": "Solicitud de otro origen.",
        "horas": "horas", "dias_uteis": "días hábiles",
    },
}
PERFIS = {
    "pt-BR": {"admin_farol": "Admin do Norte", "admin_empresa": "Admin da empresa", "operador": "Operador", "consulta": "Consulta"},
    "en": {"admin_farol": "Norte admin", "admin_empresa": "Company admin", "operador": "Operator", "consulta": "Viewer"},
    "es": {"admin_farol": "Admin de Norte", "admin_empresa": "Admin de la empresa", "operador": "Operador", "consulta": "Consulta"},
}


def idioma_valido(idioma: str | None) -> str:
    return idioma if idioma in TEXTOS else PADRAO


def t(idioma: str | None, chave: str, **valores) -> str:
    """O texto da chave no idioma (português se faltar), com os valores no lugar das chaves."""
    texto = TEXTOS[idioma_valido(idioma)].get(chave, TEXTOS[PADRAO][chave])
    return texto.format(**valores) if valores else texto


def perfil(idioma: str | None, codigo: str | None) -> str:
    return PERFIS[idioma_valido(idioma)].get(codigo or "", "")


def prazo(idioma: str | None, texto: str) -> str:
    """"72 horas" / "5 dias úteis" no idioma (o resto do texto, como a norma, fica como está)."""
    i = idioma_valido(idioma)
    return str(texto).replace("dias úteis", TEXTOS[i]["dias_uteis"]).replace("horas", TEXTOS[i]["horas"])
