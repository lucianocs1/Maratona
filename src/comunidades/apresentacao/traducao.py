"""Tradução do que o servidor mostra (Fase K): os relatórios (tela, PDF e CSV no idioma de quem gera) e as
mensagens de erro da API. O núcleo continua fazendo as contas e os textos em português; aqui o documento pronto
é traduzido por um catálogo: textos exatos e padrões (com números, nomes e datas no meio).

O que não está no catálogo fica em português (nomes de comunidade, município, pessoa e rádio nunca são
traduzidos). Em inglês, os valores em reais e as porcentagens passam para o formato com ponto decimal
("R$ 1.234,56" -> "R$ 1,234.56"; "12,5%" -> "12.5%"); o espanhol usa a vírgula, como o português.
"""

import re

PADRAO = "pt-BR"
IDIOMAS = ("pt-BR", "en", "es")
MESES = {
    "pt-BR": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
}
CURTOS = {
    "pt-BR": ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
}

# texto exato em português -> (inglês, espanhol)
EXATOS: dict[str, tuple[str, str]] = {
    # resumo dos relatórios
    "Desligamentos programados": ("Scheduled outages", "Cortes programados"),
    "Avisos gerados (por município)": ("Notices generated (per municipality)", "Avisos generados (por municipio)"),
    "Pedidos às rádios": ("Requests to radio stations", "Pedidos a las radios"),
    "Confirmados pela rádio": ("Confirmed by the station", "Confirmados por la radio"),
    "Comunidades avisadas": ("Communities notified", "Comunidades avisadas"), "UCs afetadas": ("Affected UCs", "UC afectadas"),
    "UCs com equipamento vital (contagem)": ("UCs with life-support equipment (count)", "UC con equipo de soporte vital (conteo)"),
    "Horas de desligamento": ("Outage hours", "Horas de corte"), "Tempo no ar": ("Airtime", "Tiempo al aire"),
    "Gasto do mês": ("Spent this month", "Gasto del mes"), "Gasto acumulado no ano": ("Spent so far this year", "Gasto acumulado en el año"),
    "Projeção do ano": ("Year projection", "Proyección del año"), "sem mês fechado": ("no closed month", "sin mes cerrado"),
    "Economia do mês (calculada / informada)": ("Savings this month (calculated / reported)", "Ahorro del mes (calculado / informado)"),
    "Economia acumulada no ano (calculada / informada)": ("Savings so far this year (calculated / reported)", "Ahorro acumulado en el año (calculado / informado)"),
    "Avisos no prazo": ("Notices on time", "Avisos en plazo"), "mês anterior": ("previous month", "mes anterior"),
    "mesmo mês do ano anterior": ("same month last year", "mismo mes del año anterior"),
    "Média mensal (meses fechados)": ("Monthly average (closed months)", "Promedio mensual (meses cerrados)"),
    "Projeção até dezembro": ("Projection to December", "Proyección hasta diciembre"), "Orçamento anual de rádio": ("Annual radio budget", "Presupuesto anual de radio"),
    "não definido": ("not set", "no definido"), "Orçamento usado": ("Budget used", "Presupuesto usado"),
    "Envios sem confirmação da rádio": ("Sendings not confirmed by the station", "Envíos sin confirmación de la radio"),
    "Comunidades afetadas": ("Affected communities", "Comunidades afectadas"), "Com repetição": ("With repetition", "Con repetición"),
    "Mais afetada": ("Most affected", "Más afectada"), "Horas sem luz (soma das comunidades)": ("Hours without power (sum of communities)", "Horas sin luz (suma de las comunidades)"),
    "Regra aplicada": ("Rule applied", "Regla aplicada"), "Fora do prazo": ("Late", "Fuera de plazo"),
    "Sem envio registrado": ("No sending recorded", "Sin envío registrado"),
    "Em risco (desligamento em até 3 dias sem confirmação)": ("At risk (outage within 3 days without confirmation)", "En riesgo (corte en hasta 3 días sin confirmación)"),
    "Ações no período": ("Actions in the period", "Acciones en el período"), "Pessoas": ("People", "Personas"),
    "Logins com sucesso / falha / bloqueio": ("Sign-ins successful / failed / blocked", "Accesos con éxito / fallo / bloqueo"),
    "Cadeia": ("Chain", "Cadena"), "verificada ✓": ("verified ✓", "verificada ✓"), "QUEBRADA": ("BROKEN", "ROTA"),
    "Desligamentos em 12 meses": ("Outages in 12 months", "Cortes en 12 meses"), "Horas sem luz": ("Hours without power", "Horas sin luz"),
    "UCs afetadas (soma)": ("Affected UCs (sum)", "UC afectadas (suma)"), "Endereços na comunidade (IBGE)": ("Addresses in the community (IBGE)", "Direcciones en la comunidad (IBGE)"),
    "Este mês": ("This month", "Este mes"),
    # títulos de seções
    "Avisos por semana do mês": ("Notices by week of the month", "Avisos por semana del mes"), "Desligamentos por tipo": ("Outages by type", "Cortes por tipo"),
    "Por tipo de desligamento": ("By outage type", "Por tipo de corte"), "Por município": ("By municipality", "Por municipio"),
    "Resumo por rádio": ("Summary by radio station", "Resumen por radio"), "Top 10 comunidades": ("Top 10 communities", "Top 10 comunidades"),
    "Prazos": ("Deadlines", "Plazos"), "Qualidade das planilhas": ("Spreadsheet quality", "Calidad de las planillas"),
    "Bloqueios por equipamento vital e justificativas": ("Life-support equipment blocks and justifications", "Bloqueos por equipo de soporte vital y justificaciones"),
    "Ocorrências (cancelamentos e datas alteradas)": ("Events (cancellations and date changes)", "Ocurrencias (cancelaciones y fechas cambiadas)"),
    "Atividade por pessoa": ("Activity by person", "Actividad por persona"), "Anexo: lista completa de avisos do mês": ("Appendix: full list of the month's notices", "Anexo: lista completa de avisos del mes"),
    "A conta da projeção": ("The projection math", "La cuenta de la proyección"), "Por rádio": ("By radio station", "Por radio"),
    "Ranking das rádios por custo": ("Radio stations ranked by cost", "Ranking de radios por costo"),
    "Conferência de fatura (cada envio, por rádio)": ("Invoice check (each sending, by station)", "Verificación de factura (cada envío, por radio)"),
    "Ranking por número de desligamentos": ("Ranking by number of outages", "Ranking por número de cortes"),
    "Ranking por horas sem luz": ("Ranking by hours without power", "Ranking por horas sin luz"),
    "Comunidade x tipo de desligamento": ("Community x outage type", "Comunidad x tipo de corte"),
    "Evolução mensal das 10 mais afetadas": ("Monthly trend of the 10 most affected", "Evolución mensual de las 10 más afectadas"),
    "Rádios que cobrem e confirmação": ("Stations covering and confirmation", "Radios que cubren y confirmación"),
    "Equipamento vital (contagem por município; o histórico não guarda por comunidade)": ("Life-support equipment (count per municipality; the history does not keep it per community)", "Equipo de soporte vital (conteo por municipio; el historial no lo guarda por comunidad)"),
    "Sugestões": ("Suggestions", "Sugerencias"), "% no prazo, mês a mês": ("% on time, month by month", "% en plazo, mes a mes"),
    "% no prazo por município": ("% on time by municipality", "% en plazo por municipio"), "% no prazo por tipo": ("% on time by type", "% en plazo por tipo"),
    "% no prazo por pessoa": ("% on time by person", "% en plazo por persona"), "Avisos fora do prazo": ("Late notices", "Avisos fuera de plazo"),
    "Risco: envios não confirmados com desligamento nos próximos 3 dias": ("Risk: unconfirmed sendings with an outage in the next 3 days", "Riesgo: envíos no confirmados con corte en los próximos 3 días"),
    "Verificação da cadeia": ("Chain check", "Verificación de la cadena"), "Resumo por pessoa": ("Summary by person", "Resumen por persona"),
    "Logins": ("Sign-ins", "Accesos"), "Alterações de cadastro (antes → depois)": ("Registration changes (before → after)", "Cambios de registro (antes → después)"),
    "Downloads do JSON com números de UC": ("Downloads of the JSON with UC numbers", "Descargas del JSON con números de UC"),
    "Relatórios gerados, baixados e enviados": ("Reports generated, downloaded and sent", "Informes generados, descargados y enviados"),
    "Todas as ações": ("All actions", "Todas las acciones"), "Desligamentos por mês (12 meses)": ("Outages per month (12 months)", "Cortes por mes (12 meses)"),
    "Rádios que alcançam": ("Stations that cover it", "Radios que la alcanzan"), "Último e próximo desligamento": ("Last and next outage", "Último y próximo corte"),
    "Tipos mais comuns": ("Most common types", "Tipos más comunes"), "Equipamento vital": ("Life-support equipment", "Equipo de soporte vital"),
    "Avisos que passaram pela comunidade": ("Notices that included the community", "Avisos que pasaron por la comunidad"),
    "Comunidades mais afetadas": ("Most affected communities", "Comunidades más afectadas"), "Prazos dos avisos": ("Notice deadlines", "Plazos de los avisos"),
    "Como calculamos": ("How we calculate", "Cómo calculamos"), "Comprovante do aviso": ("Notice receipt", "Comprobante del aviso"),
    "O desligamento": ("The outage", "El corte"), "Envios às rádios": ("Sendings to radio stations", "Envíos a las radios"),
    # colunas
    "Tipo": ("Type", "Tipo"), "Desligamentos": ("Outages", "Cortes"), "UCs": ("UCs", "UC"), "Horas": ("Hours", "Horas"), "Custo": ("Cost", "Costo"),
    "Município": ("Municipality", "Municipio"), "Rádio": ("Radio station", "Radio"), "Pedidos": ("Requests", "Pedidos"), "Confirmados": ("Confirmed", "Confirmados"),
    "Economia": ("Savings", "Ahorro"), "Comunidade": ("Community", "Comunidad"), "Aviso": ("Notice", "Aviso"), "Desligamento": ("Outage", "Corte"),
    "Regra": ("Rule", "Regla"), "Situação": ("Status", "Estado"), "Atraso": ("Delay", "Retraso"), "Linhas lidas": ("Rows read", "Filas leídas"),
    "Entraram": ("Included", "Entraron"), "Rejeitadas": ("Rejected", "Rechazadas"), "Corrigidas": ("Corrected", "Corregidas"), "Pessoa": ("Person", "Persona"),
    "Avisos": ("Notices", "Avisos"), "Envios": ("Sendings", "Envíos"), "Gerado": ("Generated", "Generado"), "Municípios": ("Municipalities", "Municipios"),
    "Vital": ("Life support", "Soporte vital"), "Pedido por": ("Requested by", "Pedido por"), "Total": ("Total", "Total"),
    "Valor mín.": ("Min. price", "Valor mín."), "Valor máx.": ("Max. price", "Valor máx."), "Variação": ("Range", "Variación"), "Custo total": ("Total cost", "Costo total"),
    "Custo médio": ("Average cost", "Costo medio"), "Economia calc.": ("Calc. savings", "Ahorro calc."), "Economia inf.": ("Rep. savings", "Ahorro inf."),
    "Confirmação": ("Confirmation", "Confirmación"), "Data": ("Date", "Fecha"), "Média da rádio": ("Station average", "Promedio de la radio"), "Acima": ("Above", "Por encima"),
    "Canal": ("Channel", "Canal"), "Valor": ("Price", "Valor"), "Cobrança": ("Billing", "Cobro"), "Informado por": ("Reported by", "Informado por"),
    "Comunidade (distrito)": ("Community (district)", "Comunidad (distrito)"), "Intervalo médio": ("Average interval", "Intervalo medio"),
    "Rádios que alcançam ": ("Stations that cover it ", "Radios que la alcanzan "), "Confirmação dos envios": ("Sendings confirmation", "Confirmación de los envíos"),
    "UCs com equipamento vital nos avisos": ("UCs with life-support equipment in the notices", "UC con equipo de soporte vital en los avisos"),
    "Mês": ("Month", "Mes"), "No prazo": ("On time", "En plazo"), "%": ("%", "%"), "Primeiro envio": ("First sending", "Primer envío"),
    "Antecedência real": ("Actual notice", "Antelación real"), "Exigida": ("Required", "Exigida"), "Justificativa": ("Justification", "Justificación"),
    "Gerado por": ("Generated by", "Generado por"), "Quando": ("When", "Cuándo"), "Quem": ("Who", "Quién"), "Perfil": ("Role", "Perfil"), "Empresa": ("Company", "Empresa"),
    "O quê": ("What", "Qué"), "Detalhe": ("Detail", "Detalle"), "Código": ("Code", "Código"), "Sucesso": ("Success", "Éxito"), "Falha": ("Failure", "Fallo"),
    "Bloqueio": ("Block", "Bloqueo"), "Como entrou": ("How it was included", "Cómo entró"), "outros": ("others", "otros"), "total": ("total", "total"),
    "acesso": ("sign-in", "acceso"), "planilha": ("spreadsheet", "planilla"), "aviso": ("notice", "aviso"), "radio": ("radio", "radio"),
    "cadastro": ("registration", "registro"), "relatorio": ("report", "informe"),
    "Quando ": ("When ", "Cuándo "), "Rádios": ("Radio stations", "Radios"),
    # valores
    "sem envio": ("no sending", "sin envío"), "no prazo": ("on time", "en plazo"), "fora do prazo": ("late", "fuera de plazo"), "nenhum": ("none", "ninguno"),
    "sem tipo": ("no type", "sin tipo"), "gerado": ("generated", "generado"), "cancelado": ("cancelled", "cancelado"), "inteira": ("whole", "entera"),
    "em parte": ("partly", "en parte"), "por minuto": ("per minute", "por minuto"), "valor fechado": ("flat price", "precio cerrado"),
    "sem rádio cadastrada": ("no station registered", "sin radio registrada"), "e-mail": ("email", "correo"), "cópia": ("copy", "copia"),
    "preparando": ("preparing", "preparando"), "enviado": ("sent", "enviado"), "entregue": ("delivered", "entregado"), "falhou": ("failed", "falló"),
    "confirmado": ("confirmed", "confirmado"), "Último: —": ("Last: —", "Último: —"), "Próximo: —": ("Next: —", "Próximo: —"),
    "Nenhuma rádio cadastrada alcança esta comunidade.": ("No registered station covers this community.", "Ninguna radio registrada alcanza esta comunidad."),
    "Nenhuma repetição que peça atenção neste período.": ("No repetition that needs attention in this period.", "Ninguna repetición que pida atención en este período."),
    "Cadeia de registros verificada ✓": ("Record chain verified ✓", "Cadena de registros verificada ✓"),
    "Manutenção preventiva": ("Preventive maintenance", "Mantenimiento preventivo"), "Manutenção corretiva programada": ("Scheduled corrective maintenance", "Mantenimiento correctivo programado"),
    "Obra ou ampliação da rede": ("Grid work or expansion", "Obra o ampliación de la red"), "Poda de árvores": ("Tree trimming", "Poda de árboles"),
    "Troca de equipamento": ("Equipment replacement", "Cambio de equipos"), "Outro": ("Other", "Otro"),
    "Admin do Norte": ("Norte admin", "Admin de Norte"), "Admin da empresa": ("Company admin", "Admin de la empresa"), "Operador": ("Operator", "Operador"),
    "Consulta": ("Viewer", "Consulta"),
    # subtítulo, filtros e comprovante
    "Todas as empresas": ("All companies", "Todas las empresas"), "últimos 12 meses": ("last 12 months", "últimos 12 meses"),
    "sem filtros": ("no filters", "sin filtros"), "UCs no aviso": ("UCs in the notice", "UC en el aviso"),
    "Com equipamento vital (só a contagem)": ("With life-support equipment (count only)", "Con equipo de soporte vital (solo el número)"),
    "Solicitado por": ("Requested by", "Solicitado por"), "Prazo": ("Deadline", "Plazo"), "Economia calculada": ("Calculated savings", "Ahorro calculado"),
    "Economia informada": ("Reported savings", "Ahorro informado"), "Confirmado em": ("Confirmed on", "Confirmado el"), "Por": ("By", "Por"),
    "sem envio registrado": ("no sending recorded", "sin envío registrado"),
    # como calculamos (as fórmulas, inteiras)
    "Custo de um envio: o valor informado. Por minuto no ar: valor por minuto x segundos da mensagem / 60; valor fechado: o próprio valor.":
        ("Cost of a sending: the price entered. Per minute on air: price per minute x seconds of the message / 60; flat price: the price itself.",
         "Costo de un envío: el valor informado. Por minuto al aire: valor por minuto x segundos del mensaje / 60; precio cerrado: el propio valor."),
    ("Economia calculada: só com cobrança por minuto e com o aviso de hoje (fazenda a fazenda): (segundos do aviso de hoje - segundos da "
     "mensagem do Norte) x valor por minuto / 60. Economia informada: custo antigo digitado por quem enviou - custo. Sem um dos dois, "
     "não há economia (não estimamos)."):
        ("Calculated savings: only with per-minute billing and with today's notice (farm by farm): (seconds of today's notice - seconds of the "
         "Norte message) x price per minute / 60. Reported savings: old cost typed by whoever sent it - cost. Without one of the two, there are "
         "no savings (we do not estimate).",
         "Ahorro calculado: solo con cobro por minuto y con el aviso actual (finca por finca): (segundos del aviso actual - segundos del "
         "mensaje de Norte) x valor por minuto / 60. Ahorro informado: costo antiguo escrito por quien envió - costo. Sin uno de los dos, "
         "no hay ahorro (no estimamos)."),
    ("Projeção do ano: gasto acumulado até o mês do relatório + média dos meses já fechados x meses que faltam até dezembro. "
     "Sem mês fechado, não há projeção."):
        ("Year projection: amount spent up to the report month + average of the months already closed x months left until December. "
         "Without a closed month, there is no projection.",
         "Proyección del año: gasto acumulado hasta el mes del informe + promedio de los meses ya cerrados x meses que faltan hasta diciembre. "
         "Sin mes cerrado, no hay proyección."),
    ("No prazo: o primeiro envio à rádio saiu pelo menos 72 horas antes do início do desligamento (5 dias úteis quando há equipamento "
     "vital; feriados não entram). % no prazo = avisos no prazo / avisos com envio. Aviso sem envio fica fora da conta."):
        ("On time: the first sending to the radio station went out at least 72 hours before the outage starts (5 business days when there is "
         "life-support equipment; holidays do not count). % on time = notices on time / notices with a sending. A notice without a sending is left out.",
         "En plazo: el primer envío a la radio salió al menos 72 horas antes del inicio del corte (5 días hábiles cuando hay equipo de "
         "soporte vital; los feriados no cuentan). % en plazo = avisos en plazo / avisos con envío. Un aviso sin envío queda fuera de la cuenta."),
    ("Frequência: quantos desligamentos a comunidade teve no período; repetição = N ou mais desligamentos dentro de D dias "
     "(configuração da empresa). Intervalo médio: média dos dias entre um desligamento e o seguinte."):
        ("Frequency: how many outages the community had in the period; repetition = N or more outages within D days (company settings). "
         "Average interval: average number of days between one outage and the next.",
         "Frecuencia: cuántos cortes tuvo la comunidad en el período; repetición = N o más cortes dentro de D días (configuración de la empresa). "
         "Intervalo medio: promedio de días entre un corte y el siguiente."),
    ("Duração: fim - início do horário do aviso (\"8h às 14h\" = 6 h). Horas sem luz de uma comunidade: soma das durações dos "
     "desligamentos em que ela entrou (inteira ou em parte)."):
        ("Duration: end - start of the notice time (\"8h às 14h\" = 6 h). Hours without power of a community: sum of the durations of the "
         "outages it was part of (whole or partly).",
         "Duración: fin - inicio del horario del aviso (\"8h às 14h\" = 6 h). Horas sin luz de una comunidad: suma de las duraciones de los "
         "cortes en los que entró (entera o en parte)."),
    ("Comparações: (atual - anterior) / anterior; seta para cima quando aumentou, para baixo quando diminuiu; sem o número "
     "anterior (ou zero), não há porcentagem."):
        ("Comparisons: (current - previous) / previous; arrow up when it increased, down when it decreased; without the previous number "
         "(or zero), there is no percentage.",
         "Comparaciones: (actual - anterior) / anterior; flecha hacia arriba cuando aumentó, hacia abajo cuando disminuyó; sin el número "
         "anterior (o cero), no hay porcentaje."),
    "Cada desligamento, e os envios dele, contam no mês em que o aviso foi gerado.":
        ("Each outage, and its sendings, count in the month in which the notice was generated.",
         "Cada corte, y sus envíos, cuentan en el mes en que se generó el aviso."),
    "Orçamento usado = gasto acumulado / orçamento anual.": ("Budget used = amount spent so far / annual budget.", "Presupuesto usado = gasto acumulado / presupuesto anual."),
    "Sugestões: mesmo tipo de desligamento 2 ou mais vezes em 60 dias, ou repetição acima do limite da empresa.":
        ("Suggestions: same outage type 2 or more times in 60 days, or repetition above the company limit.",
         "Sugerencias: mismo tipo de corte 2 o más veces en 60 días, o repetición por encima del límite de la empresa."),
    "Justificativa de atraso: o Norte ainda não pede; a coluna fica com \"—\".":
        ("Justification for delays: Norte does not ask for it yet; the column shows \"—\".",
         "Justificación de retraso: Norte aún no la pide; la columna queda con \"—\"."),
    "Cada linha da auditoria guarda o hash da anterior; a verificação refaz a conta da primeira à última.":
        ("Each audit row keeps the hash of the previous one; the check redoes the math from the first to the last.",
         "Cada fila de la auditoría guarda el hash de la anterior; la verificación rehace la cuenta de la primera a la última."),
    "Tipos: acesso, planilha, aviso, rádio, cadastro, relatório e outros, pelo começo do nome da ação.":
        ("Types: sign-in, spreadsheet, notice, radio, registration, report and others, by the start of the action name.",
         "Tipos: acceso, planilla, aviso, radio, registro, informe y otros, por el comienzo del nombre de la acción."),
    # mensagens de erro mais comuns da API (as que não têm partes variáveis)
    "Entre com o seu e-mail e senha.": ("Sign in with your email and password.", "Entre con su correo y contraseña."),
    "Seu perfil não tem acesso a isto.": ("Your role does not have access to this.", "Su perfil no tiene acceso a esto."),
    "Troque a senha temporária antes de continuar.": ("Change the temporary password before continuing.", "Cambie la contraseña temporal antes de continuar."),
    "E-mail ou senha incorretos. Após 5 tentativas erradas o acesso fica suspenso por 15 minutos.":
        ("Incorrect email or password. After 5 wrong attempts, access is suspended for 15 minutes.",
         "Correo o contraseña incorrectos. Después de 5 intentos fallidos, el acceso queda suspendido por 15 minutos."),
    "Acesso desativado. Fale com o administrador da sua empresa.": ("Access disabled. Contact your company administrator.", "Acceso desactivado. Hable con el administrador de su empresa."),
    "A senha atual não confere.": ("The current password does not match.", "La contraseña actual no coincide."),
    "A senha nova tem de ser diferente da atual.": ("The new password must be different from the current one.", "La contraseña nueva tiene que ser distinta de la actual."),
    "A senha repete caracteres demais.": ("The password repeats too many characters.", "La contraseña repite demasiados caracteres."),
    "A senha não pode conter o seu e-mail.": ("The password cannot contain your email.", "La contraseña no puede contener su correo."),
    "Tentativas demais deste endereço. Espere alguns minutos.": ("Too many attempts from this address. Wait a few minutes.", "Demasiados intentos desde esta dirección. Espere unos minutos."),
    "Origem não permitida.": ("Origin not allowed.", "Origen no permitido."), "E-mail inválido.": ("Invalid email.", "Correo inválido."),
    "Já existe um usuário com este e-mail.": ("A user with this email already exists.", "Ya existe un usuario con este correo."),
    "Perfil inválido.": ("Invalid role.", "Perfil inválido."), "Nome: de 2 a 120 caracteres.": ("Name: 2 to 120 characters.", "Nombre: de 2 a 120 caracteres."),
    "Usuário não encontrado nesta empresa.": ("User not found in this company.", "Usuario no encontrado en esta empresa."),
    "Este é o último admin ativo da empresa: cadastre outro admin antes de mudar o perfil ou bloquear.":
        ("This is the company's last active admin: register another admin before changing the role or blocking.",
         "Este es el último admin activo de la empresa: registre otro admin antes de cambiar el perfil o bloquear."),
    "Empresa não encontrada.": ("Company not found.", "Empresa no encontrada."), "Já existe uma empresa com esta sigla.": ("A company with this acronym already exists.", "Ya existe una empresa con esta sigla."),
    "Já existe uma empresa com este CNPJ.": ("A company with this CNPJ already exists.", "Ya existe una empresa con este CNPJ."),
    "CNPJ inválido: confira os dígitos verificadores (aceita o alfanumérico).": ("Invalid CNPJ: check the check digits (alphanumeric accepted).", "CNPJ inválido: revise los dígitos verificadores (acepta el alfanumérico)."),
    "Sigla: de 2 a 10 letras ou números.": ("Acronym: 2 to 10 letters or digits.", "Sigla: de 2 a 10 letras o números."),
    "Domínio de e-mail inválido (ex.: empresa.com.br).": ("Invalid email domain (e.g. company.com).", "Dominio de correo inválido (ej.: empresa.com)."),
    "Nada mudou nos dados da empresa.": ("Nothing changed in the company data.", "Nada cambió en los datos de la empresa."),
    "Nome da rádio: de 2 a 80 caracteres.": ("Station name: 2 to 80 characters.", "Nombre de la radio: de 2 a 80 caracteres."),
    "Informe o e-mail ou o WhatsApp da rádio.": ("Enter the station email or WhatsApp.", "Indique el correo o el WhatsApp de la radio."),
    "WhatsApp da rádio: de 10 a 13 algarismos, com o DDD (e o 55 do Brasil, se quiser).": ("Station WhatsApp: 10 to 13 digits, with the area code (and Brazil's 55, if you want).", "WhatsApp de la radio: de 10 a 13 dígitos, con el código de área (y el 55 de Brasil, si quiere)."),
    "Já existe uma rádio com este nome nesta empresa.": ("A station with this name already exists in this company.", "Ya existe una radio con este nombre en esta empresa."),
    "Já existe outra rádio com este nome nesta empresa.": ("Another station with this name already exists in this company.", "Ya existe otra radio con este nombre en esta empresa."),
    "Rádio não encontrada nesta empresa.": ("Station not found in this company.", "Radio no encontrada en esta empresa."),
    "Este pedido de rádio já foi atendido ou recusado.": ("This station request was already fulfilled or declined.", "Esta solicitud de radio ya fue atendida o rechazada."),
    "Já existe um pedido aberto para esta rádio nesta cidade.": ("There is already an open request for this station in this city.", "Ya existe una solicitud abierta para esta radio en esta ciudad."),
    "Cidade da rádio: de 2 a 80 caracteres.": ("Station city: 2 to 80 characters.", "Ciudad de la radio: de 2 a 80 caracteres."),
    "Contato da rádio: o e-mail ou o telefone da rádio, com o DDD.": ("Station contact: the station email or phone, with the area code.", "Contacto de la radio: el correo o el teléfono de la radio, con el código de área."),
    "Pedido não encontrado nesta empresa.": ("Request not found in this company.", "Solicitud no encontrada en esta empresa."),
    "Aviso não encontrado nesta empresa.": ("Notice not found in this company.", "Aviso no encontrado en esta empresa."),
    "Este aviso já foi cancelado.": ("This notice was already cancelled.", "Este aviso ya fue cancelado."),
    "Este desligamento foi cancelado: nada é enviado.": ("This outage was cancelled: nothing is sent.", "Este corte fue cancelado: no se envía nada."),
    "Informe o valor do envio (R$).": ("Enter the price of the sending (R$).", "Indique el valor del envío (R$)."),
    "O texto não pode ter números longos (UC, CPF, telefone de cliente), e-mail nem site.": ("The text cannot have long numbers (UC, CPF, customer phone), email or website.", "El texto no puede tener números largos (UC, CPF, teléfono de cliente), correo ni sitio web."),
    "Texto do aviso: de 1 a 3.000 caracteres.": ("Notice text: 1 to 3,000 characters.", "Texto del aviso: de 1 a 3.000 caracteres."),
    "O envio por e-mail está desligado neste servidor. Use o WhatsApp ou copie a mensagem.": ("Sending by email is turned off on this server. Use WhatsApp or copy the message.", "El envío por correo está desactivado en este servidor. Use WhatsApp o copie el mensaje."),
    "O envio por e-mail está desligado neste servidor.": ("Sending by email is turned off on this server.", "El envío por correo está desactivado en este servidor."),
    "O áudio do aviso está desligado neste servidor.": ("Notice audio is turned off on this server.", "El audio del aviso está desactivado en este servidor."),
    "Sem voz com licença adequada para este idioma: o aviso vai sem áudio (veja ORIGEM.md).": ("No voice with a suitable license for this language: the notice goes without audio (see ORIGEM.md).", "Sin voz con licencia adecuada para este idioma: el aviso va sin audio (vea ORIGEM.md)."),
    "Município não encontrado neste aviso.": ("Municipality not found in this notice.", "Municipio no encontrado en este aviso."),
    "Arquivo não encontrado nesta empresa.": ("File not found in this company.", "Archivo no encontrado en esta empresa."),
    "O modelo da mensagem não pode ficar vazio.": ("The message template cannot be empty.", "La plantilla del mensaje no puede quedar vacía."),
    "Nome da empresa na mensagem: de 2 a 120 caracteres.": ("Company name in the message: 2 to 120 characters.", "Nombre de la empresa en el mensaje: de 2 a 120 caracteres."),
    # área de atuação (mapa das empresas)
    "A área de atuação da empresa não está cadastrada: nenhum aviso pode ser criado. Peça ao Admin do Norte.":
        ("The company's service area is not registered: no notice can be created. Ask the Norte Admin.",
         "El área de actuación de la empresa no está registrada: no se puede crear ningún aviso. Pida al Admin de Norte."),
    "Município fora da área de atuação da empresa.": ("Municipality outside the company's service area.", "Municipio fuera del área de actuación de la empresa."),
    "Nada mudou na área de atuação.": ("Nothing changed in the service area.", "Nada cambió en el área de actuación."),
    "Envie a lista de municípios.": ("Send the list of municipalities.", "Envíe la lista de municipios."),
    "Código de município inválido (use os 7 dígitos do IBGE).": ("Invalid municipality code (use the 7 IBGE digits).", "Código de municipio inválido (use los 7 dígitos del IBGE)."),
    "UF inválida.": ("Invalid state.", "Estado inválido."),
    "Arquivo vazio.": ("Empty file.", "Archivo vacío."),
    "O arquivo tem script, DTD ou entidade: recusado por segurança.": ("The file has a script, DTD or entity: refused for security.", "El archivo tiene script, DTD o entidad: rechazado por seguridad."),
    "Envie um arquivo .kml ou .geojson.": ("Send a .kml or .geojson file.", "Envíe un archivo .kml o .geojson."),
    "O arquivo não é um KML válido.": ("The file is not a valid KML.", "El archivo no es un KML válido."),
    "O arquivo não é um GeoJSON válido.": ("The file is not a valid GeoJSON.", "El archivo no es un GeoJSON válido."),
    "O arquivo tem só pontos ou linhas: a área precisa de polígonos.": ("The file has only points or lines: the area needs polygons.", "El archivo solo tiene puntos o líneas: el área necesita polígonos."),
    "Só polígonos: o arquivo tem pontos, linhas ou outro tipo de geometria.": ("Polygons only: the file has points, lines or another geometry type.", "Solo polígonos: el archivo tiene puntos, líneas u otro tipo de geometría."),
    "Geometria ilegível no GeoJSON.": ("Unreadable geometry in the GeoJSON.", "Geometría ilegible en el GeoJSON."),
    "Coordenadas do KML ilegíveis.": ("Unreadable KML coordinates.", "Coordenadas del KML ilegibles."),
    "Nenhum polígono no arquivo.": ("No polygon in the file.", "Ningún polígono en el archivo."),
    "Polígonos demais no arquivo.": ("Too many polygons in the file.", "Demasiados polígonos en el archivo."),
    "Há polígono fora do Brasil (confira se as coordenadas estão em longitude, latitude).":
        ("There is a polygon outside Brazil (check that coordinates are longitude, latitude).", "Hay un polígono fuera de Brasil (verifique que las coordenadas estén en longitud, latitud)."),
    "Os polígonos do arquivo não têm área.": ("The polygons in the file have no area.", "Los polígonos del archivo no tienen área."),
    "Nenhum município do IBGE tem pelo menos metade da área dentro dos polígonos do arquivo.":
        ("No IBGE municipality has at least half of its area inside the file's polygons.", "Ningún municipio del IBGE tiene al menos la mitad del área dentro de los polígonos del archivo."),
    "fora da área de atuação da empresa": ("outside the company's service area", "fuera del área de actuación de la empresa"),
    "Descreva o problema (pelo menos 10 caracteres).": ("Describe the problem (at least 10 characters).", "Describa el problema (al menos 10 caracteres)."),
    "Sem dado pessoal: tire e-mail, telefone, número longo e endereço de site.": ("No personal data: remove e-mail, phone, long numbers and website addresses.", "Sin datos personales: quite correo, teléfono, números largos y direcciones de sitios."),
    # simulador de economia
    "Simulador de economia com rádio": ("Radio savings simulator", "Simulador de ahorro con radio"),
    "Redução do tempo no ar": ("Reduction in airtime", "Reducción del tiempo al aire"),
    "De onde vem a redução": ("Where the reduction comes from", "De dónde viene la reducción"),
    "Gasto mensal com rádio": ("Monthly radio spending", "Gasto mensual con radio"),
    "Parte do gasto cobrada por tempo": ("Share of spending billed by time", "Parte del gasto cobrada por tiempo"),
    "Economia mensal estimada": ("Estimated monthly savings", "Ahorro mensual estimado"),
    "Economia anual estimada": ("Estimated annual savings", "Ahorro anual estimado"),
    "Economia anual no cenário conservador": ("Annual savings in the conservative scenario", "Ahorro anual en el escenario conservador"),
    "Já economizado (envios registrados)": ("Already saved (recorded sendings)", "Ya ahorrado (envíos registrados)"),
    "não informado": ("not provided", "no informado"),
    "Quem será desligado": ("Who will lose power", "Quiénes quedarán sin energía"),
    "medição de validação (Leopoldina)": ("validation measurement (Leopoldina)", "medición de validación (Leopoldina)"),
    "média real de 1 aviso da empresa": ("real average of 1 company notice", "promedio real de 1 aviso de la empresa"),
    "Origem dos valores": ("Source of the values", "Origen de los valores"),
    "Origem dos valores: até 120 caracteres, sem e-mail, site nem número longo.": ("Source of the values: up to 120 characters, no e-mail, website or long number.",
                                                                               "Origen de los valores: hasta 120 caracteres, sin correo, sitio ni número largo."),
    "Ainda não há avisos com o aviso de hoje no período: a redução usada é a da medição de validação (Leopoldina, 44 s -> 14 s).":
        ("There are no notices with today's notice in the period yet: the reduction used is the validation measurement (Leopoldina, 44 s -> 14 s).",
         "Aún no hay avisos con el aviso de hoy en el período: la reducción usada es la de la medición de validación (Leopoldina, 44 s -> 14 s)."),
    "O gasto mensal com rádio ainda não foi informado: o Admin da empresa preenche no simulador.":
        ("Monthly radio spending has not been provided yet: the company Admin fills it in on the simulator.",
         "El gasto mensual con radio aún no fue informado: el Admin de la empresa lo completa en el simulador."),
    "Cenários": ("Scenarios", "Escenarios"), "Faixa": ("Range", "Rango"), "Cenário": ("Scenario", "Escenario"),
    "Gasto mensal": ("Monthly spending", "Gasto mensual"), "Cobrado por tempo": ("Billed by time", "Cobrado por tiempo"),
    "Economia mensal": ("Monthly savings", "Ahorro mensual"), "Economia anual": ("Annual savings", "Ahorro anual"),
    "mínimo": ("minimum", "mínimo"), "máximo": ("maximum", "máximo"), "da empresa": ("company setting", "de la empresa"),
    "conservador": ("conservative", "conservador"),
    "Já economizado de fato": ("Actually saved so far", "Ya ahorrado de hecho"),
    "Tempo no ar usado na redução": ("Airtime used for the reduction", "Tiempo al aire usado en la reducción"),
    ("Redução = (segundos do aviso tradicional estimado - segundos do aviso do Norte) / segundos do aviso tradicional, somando os "
     "avisos do período cuja planilha trouxe a coluna local (o aviso de hoje, fazenda a fazenda)."):
        ("Reduction = (seconds of the estimated traditional notice - seconds of the Norte notice) / seconds of the traditional notice, adding up "
         "the period's notices whose spreadsheet had the local column (today's notice, farm by farm).",
         "Reducción = (segundos del aviso tradicional estimado - segundos del aviso del Norte) / segundos del aviso tradicional, sumando los "
         "avisos del período cuya planilla trajo la columna local (el aviso de hoy, finca por finca)."),
    "Sem esses avisos no período, vale a medição de validação (Leopoldina): 44 s -> 14 s, redução de 68,2%.":
        ("Without such notices in the period, the validation measurement (Leopoldina) applies: 44 s -> 14 s, a 68.2% reduction.",
         "Sin esos avisos en el período, vale la medición de validación (Leopoldina): 44 s -> 14 s, reducción del 68,2%."),
    "Economia mensal = gasto mensal com rádio x parte do gasto cobrada por tempo x redução. Economia anual = economia mensal x 12.":
        ("Monthly savings = monthly radio spending x share of spending billed by time x reduction. Annual savings = monthly savings x 12.",
         "Ahorro mensual = gasto mensual con radio x parte del gasto cobrada por tiempo x reducción. Ahorro anual = ahorro mensual x 12."),
    "Cenário conservador: só 50% do gasto é cobrado por tempo (o resto não muda com o tamanho do aviso).":
        ("Conservative scenario: only 50% of spending is billed by time (the rest does not change with the length of the notice).",
         "Escenario conservador: solo el 50% del gasto se cobra por tiempo (el resto no cambia con el largo del aviso)."),
    "Já economizado = economia calculada + economia informada dos envios registrados no período (envio de aviso cancelado também conta).":
        ("Already saved = calculated savings + reported savings of the sendings recorded in the period (a sending of a cancelled notice also counts).",
         "Ya ahorrado = ahorro calculado + ahorro informado de los envíos registrados en el período (el envío de un aviso cancelado también cuenta)."),
    "É uma simulação: o gasto mensal e a parte cobrada por tempo são informados pelo Admin da empresa; a redução vem dos avisos.":
        ("This is a simulation: monthly spending and the share billed by time are provided by the company Admin; the reduction comes from the notices.",
         "Es una simulación: el gasto mensual y la parte cobrada por tiempo los informa el Admin de la empresa; la reducción viene de los avisos."),
    "Gasto máximo: igual ou maior que o mínimo.": ("Maximum spending: equal to or greater than the minimum.", "Gasto máximo: igual o mayor que el mínimo."),
}

# padrões: (expressão em português, inglês, espanhol); {1}, {2}... são os grupos; {mes1} é o grupo 1 como mês por extenso
PADROES: list[tuple[str, str, str]] = [
    # simulador de economia
    (r"média real de (\d+) avisos da empresa", "real average of {1} company notices", "promedio real de {1} avisos de la empresa"),
    (r"(-?R\$ [\d.,]+) a (-?R\$ [\d.,]+)", "{1} to {2}", "{1} a {2}"),
    (r"(-?R\$ [\d.,]+) calculada \+ (-?R\$ [\d.,]+) informada = (-?R\$ [\d.,]+), em (\d+) envio\(s\) do período\.",
     "{1} calculated + {2} reported = {3}, in {4} sending(s) in the period.", "{1} calculado + {2} informado = {3}, en {4} envío(s) del período."),
    (r"Aviso tradicional: (\d+) s; aviso do Norte: (\d+) s\.", "Traditional notice: {1} s; Norte notice: {2} s.", "Aviso tradicional: {1} s; aviso del Norte: {2} s."),
    (r"Conta \((mínimo|máximo), (da empresa|conservador)\): (-?R\$ [\d.,]+) x ([\d,]+%) x (-?[\d,]+%) = (-?R\$ [\d.,]+) por mês; x 12 = (-?R\$ [\d.,]+) por ano\.",
     "Calculation ({1}, {2}): {3} x {4} x {5} = {6} per month; x 12 = {7} per year.",
     "Cálculo ({1}, {2}): {3} x {4} x {5} = {6} por mes; x 12 = {7} por año."),
    (r'Nenhum acesso no período\. Há (\d+) ação\(ões\) de outro tipo; desmarque "Só acessos" para vê-las\.',
     'No sign-ins in the period. There are {1} action(s) of another type; uncheck "Sign-ins only" to see them.',
     'Ningún acceso en el período. Hay {1} acción(es) de otro tipo; desmarque "Solo accesos" para verlas.'),
    (r"Arquivo grande demais \(máximo (\d+) MB\)\.", "File too large (maximum {1} MB).", "Archivo demasiado grande (máximo {1} MB)."),
    (r"No máximo (\d+) municípios\.", "At most {1} municipalities.", "Como máximo {1} municipios."),
    (r"(\d+) código\(s\) que não são municípios do IBGE\.", "{1} code(s) that are not IBGE municipalities.", "{1} código(s) que no son municipios del IBGE."),
    (r"Relatório mensal - (\w+) de (\d{4})", "Monthly report - {mes1} {2}", "Informe mensual - {mes1} de {2}"),
    (r"Gasto mês a mês em (\d{4}) \(projeção até dezembro\)", "Spending month by month in {1} (projection to December)", "Gasto mes a mes en {1} (proyección hasta diciembre)"),
    (r"Custos por rádio - (\d{4})", "Costs by radio station - {1}", "Costos por radio - {1}"),
    (r"Gasto por rádio, mês a mês \((\d{4})\)", "Spending by station, month by month ({1})", "Gasto por radio, mes a mes ({1})"),
    (r"Gasto acumulado em (\d{4}) \(até (\w+)\)", "Spent so far in {1} (to {curto2})", "Gasto acumulado en {1} (hasta {curto2})"),
    (r"mesmo período de (\d{4})", "same period of {1}", "mismo período de {1}"),
    (r"Alertas de preço \(custo mais de (\d+)% acima da média da rádio\)", "Price alerts (cost more than {1}% above the station average)", "Alertas de precio (costo más de {1}% por encima del promedio de la radio)"),
    (r"(\d+) envio\(s\) com custo mais de (\d+)% acima da média da própria rádio\.", "{1} sending(s) costing more than {2}% above the station's own average.", "{1} envío(s) con costo más de {2}% por encima del promedio de la propia radio."),
    (r"(\d+) aviso\(s\) fora do prazo\.", "{1} late notice(s).", "{1} aviso(s) fuera de plazo."),
    (r"(\d+) envio\(s\) em risco\.", "{1} sending(s) at risk.", "{1} envío(s) en riesgo."),
    (r"(\d+) comunidade\(s\) com (\d+)\+ desligamentos em (\d+) dias\.", "{1} community(ies) with {2}+ outages in {3} days.", "{1} comunidad(es) con {2}+ cortes en {3} días."),
    (r"Repetição: (\d+) ou mais desligamentos em (\d+) dias", "Repetition: {1} or more outages in {2} days", "Repetición: {1} o más cortes en {2} días"),
    (r"Maior número em (\d+) dias", "Highest count in {1} days", "Mayor número en {1} días"),
    (r"A projeção do ano \((.+)\) passa do orçamento \((.+)\)\.", "The year projection ({1}) exceeds the budget ({2}).", "La proyección del año ({1}) supera el presupuesto ({2})."),
    (r"Projeção deste relatório: (.+)\.", "Projection in this report: {1}.", "Proyección de este informe: {1}."),
    (r"Projeção: (.+)\.", "Projection: {1}.", "Proyección: {1}."),
    (r"(.+) \(acumulado\) \+ (.+) \(média de (\d+) mês\(es\) fechado\(s\)\) x (\d+) = (.+)", "{1} (so far) + {2} (average of {3} closed month(s)) x {4} = {5}",
     "{1} (acumulado) + {2} (promedio de {3} mes(es) cerrado(s)) x {4} = {5}"),
    (r"acumulado (.+); sem mês fechado, não há projeção", "so far {1}; without a closed month there is no projection", "acumulado {1}; sin mes cerrado no hay proyección"),
    (r"Alerta de preço: custo do envio > média de custo da própria rádio no ano x \(1 \+ (\d+)%\)\.",
     "Price alert: sending cost > the station's own average cost in the year x (1 + {1}%).", "Alerta de precio: costo del envío > costo promedio de la propia radio en el año x (1 + {1}%)."),
    (r"(\d+) \((.+) com envio\)", "{1} ({2} with sending)", "{1} ({2} con envío)"),
    (r"(.+) \((\d+) de (\d+) com envio\)", "{1} ({2} of {3} with sending)", "{1} ({2} de {3} con envío)"),
    (r"(.+) \((\d+) de (\d+)\)", "{1} ({2} of {3})", "{1} ({2} de {3})"),
    (r"(\d+) de (\d+)", "{1} of {2}", "{1} de {2}"),
    (r"(\d+) horas; (\d+) dias úteis com equipamento vital", "{1} hours; {2} business days with life-support equipment", "{1} horas; {2} días hábiles con equipo de soporte vital"),
    (r"(\d+) horas", "{1} hours", "{1} horas"), (r"(\d+) dias úteis", "{1} business days", "{1} días hábiles"),
    (r"Antecedência mínima de (\d+) horas; com equipamento vital, (\d+) dias úteis \(REN ANEEL 1\.000/2021, art\. 436\)\. O momento do aviso é o primeiro envio à rádio\.",
     "Minimum notice of {1} hours; with life-support equipment, {2} business days (REN ANEEL 1,000/2021, art. 436). The notice moment is the first sending to the radio station.",
     "Antelación mínima de {1} horas; con equipo de soporte vital, {2} días hábiles (REN ANEEL 1.000/2021, art. 436). El momento del aviso es el primer envío a la radio."),
    (r"(.+) h \((.+)\)", "{1} h ({2})", "{1} h ({2})"),
    (r"(.+) \((.+)\) teve (\d+) desligamentos por (.+) em (\d+) dias: avaliar juntar os serviços\.",
     "{1} ({2}) had {3} outages for {4} in {5} days: consider combining the work.", "{1} ({2}) tuvo {3} cortes por {4} en {5} días: evaluar unir los servicios."),
    (r"(.+) \((.+)\) teve (\d+) desligamentos em até (\d+) dias: avisar com mais antecedência e conversar com a comunidade\.",
     "{1} ({2}) had {3} outages within {4} days: give more advance notice and talk with the community.",
     "{1} ({2}) tuvo {3} cortes en hasta {4} días: avisar con más antelación y conversar con la comunidad."),
    (r"(.+) dias", "{1} days", "{1} días"),
    (r"semana (\d)", "week {1}", "semana {1}"),
    (r"A cadeia NÃO confere a partir da linha (.+) \((.+)\)", "The chain does NOT match from row {1} ({2})", "La cadena NO coincide a partir de la fila {1} ({2})"),
    (r"Auditoria geral de acessos - (.+)", "General sign-in audit - {1}", "Auditoría general de accesos - {1}"),
    (r"Relatório de auditoria - (.+)", "Audit report - {1}", "Informe de auditoría - {1}"),
    (r"Comunidade (.+) - (.*)", "Community {1} - {2}", "Comunidad {1} - {2}"),
    (r"Último: (.+) \(aviso nº (\d+), (.+)\)", "Last: {1} (notice no. {2}, {3})", "Último: {1} (aviso n.º {2}, {3})"),
    (r"Próximo: (.+) \(aviso nº (\d+), (.+)\)", "Next: {1} (notice no. {2}, {3})", "Próximo: {1} (aviso n.º {2}, {3})"),
    (r"Até (\d+) UC\(s\) com equipamento vital nos avisos do município \(o histórico guarda a contagem por município\)\.",
     "Up to {1} UC(s) with life-support equipment in the municipality's notices (the history keeps the count per municipality).",
     "Hasta {1} UC con equipo de soporte vital en los avisos del municipio (el historial guarda el conteo por municipio)."),
    (r"nº (\d+)", "no. {1}", "n.º {1}"),
    (r"nº (\d+) - código (.+)", "no. {1} - code {2}", "n.º {1} - código {2}"),
    (r"(.*) - desligamento de (.+)", "{1} - outage on {2}", "{1} - corte del {2}"),
    (r"(\d+) dias úteis \(equipamento vital\)", "{1} business days (life-support equipment)", "{1} días hábiles (equipo de soporte vital)"),
    (r"(.+): fora do prazo \((.+) h\)", "{1}: late ({2} h)", "{1}: fuera de plazo ({2} h)"),
    (r"(.+): (no prazo|sem envio registrado)", "{1}: {2}", "{1}: {2}"),
    (r"(\w+) de (\d{4})", "{mes1} {2}", "{mes1} de {2}"),
    (r"(\d{2}/\d{2}/\d{4}) a (\d{2}/\d{2}/\d{4})", "{1} to {2}", "{1} a {2}"),
    (r"Comprovante do aviso nº (\d+)", "Receipt of notice no. {1}", "Comprobante del aviso n.º {1}"),
    (r"(.+): (\d+) UCs, (\d+) com equipamento vital", "{1}: {2} UCs, {3} with life-support equipment", "{1}: {2} UC, {3} con equipo de soporte vital"),
    (r"Pedidos às rádios: (.+)", "Requests to radio stations: {1}", "Pedidos a las radios: {1}"),
    (r"(\w+)/(\d{2})", "{curto1}/{2}", "{curto1}/{2}"),
    # erros da API com partes variáveis
    (r"Só e-mails @(.+) podem ser cadastrados nesta empresa\.", "Only @{1} emails can be registered in this company.", "Solo se pueden registrar correos @{1} en esta empresa."),
    (r"Só e-mails @(.+) podem receber relatórios: (.+)\.", "Only @{1} emails can receive reports: {2}.", "Solo correos @{1} pueden recibir informes: {2}."),
    (r"A senha precisa ter pelo menos (\d+) caracteres\.", "The password must have at least {1} characters.", "La contraseña debe tener al menos {1} caracteres."),
    (r"Este aviso já foi gerado com esta conferência \(aviso nº (\d+)\)\. Para outro aviso, confira a planilha de novo\.",
     "This notice was already generated with this check (notice no. {1}). For another notice, check the spreadsheet again.",
     "Este aviso ya fue generado con esta verificación (aviso n.º {1}). Para otro aviso, verifique la planilla de nuevo."),
    (r"Este envio acabou de ser registrado \(envio nº (\d+)\)\. Para repetir, espere um minuto\.",
     "This sending was just recorded (sending no. {1}). To repeat it, wait a minute.", "Este envío acaba de registrarse (envío n.º {1}). Para repetirlo, espere un minuto."),
    (r"O aviso já está com a data (.+)\.", "The notice already has the date {1}.", "El aviso ya tiene la fecha {1}."),
    (r"A empresa já está (ativa|suspensa)\.", "The company is already {1}.", "La empresa ya está {1}."),
    (r"Destinatários: de 1 a (\d+) e-mails\.", "Recipients: 1 to {1} emails.", "Destinatarios: de 1 a {1} correos."),
    (r"Limite de (\d+) envios de relatório por hora atingido\.", "Limit of {1} report sendings per hour reached.", "Límite de {1} envíos de informe por hora alcanzado."),
    (r"Limite de (\d+) e-mails para rádios por hora atingido\. Tente mais tarde\.", "Limit of {1} emails to radio stations per hour reached. Try later.", "Límite de {1} correos a radios por hora alcanzado. Inténtelo más tarde."),
    (r"Ocorreu um erro e nada foi gerado \(código (ERR-\w+)\)\.", "An error occurred and nothing was generated (code {1}).", "Ocurrió un error y no se generó nada (código {1})."),
    (r"Confira o campo (.+): preencha este campo\.", "Check the field {1}: fill in this field.", "Revise el campo {1}: complete este campo."),
    (r"Confira o campo (.+): no máximo (.+)\.", "Check the field {1}: at most {2}.", "Revise el campo {1}: como máximo {2}."),
    (r"Confira o campo (.+): no mínimo (.+)\.", "Check the field {1}: at least {2}.", "Revise el campo {1}: como mínimo {2}."),
    (r"Confira o campo (.+): (.+)", "Check the field {1}: {2}", "Revise el campo {1}: {2}"),
    (r"E-mail da rádio: (.+)", "Station email: {1}", "Correo de la radio: {1}"),
    (r"Tipo de desligamento: (.+)", "Type of outage: {1}", "Tipo de corte: {1}"),
    (r"Motivo do cancelamento: (.+)", "Cancellation reason: {1}", "Motivo de la cancelación: {1}"),
    (r"Observação: (.+)", "Note: {1}", "Observación: {1}"),
    (r"Motivo da recusa: (.+)", "Reason for declining: {1}", "Motivo del rechazo: {1}"),
    (r"Valor: (.+)", "Price: {1}", "Valor: {1}"),
]
_PADROES = [(re.compile(f"^{p}$"), en, es) for p, en, es in PADROES]
_REAIS = re.compile(r"R\$ ?(-?)(\d{1,3}(?:\.\d{3})*),(\d{2})")
_PCT = re.compile(r"(\d+),(\d+)%")


def _mes(nome: str, idioma: str, tabela: dict) -> str:
    pt = [m.lower() for m in tabela["pt-BR"]]
    return tabela[idioma][pt.index(nome.lower())] if nome.lower() in pt else nome


def _numeros_en(t: str) -> str:
    t = _REAIS.sub(lambda m: f"R$ {m.group(1)}{m.group(2).replace('.', ',')}.{m.group(3)}", t)
    return _PCT.sub(r"\1.\2%", t)


def texto(t: str, idioma: str | None) -> str:
    """Um texto em português no idioma (o que não estiver no catálogo fica como está)."""
    if idioma not in ("en", "es") or not isinstance(t, str) or not t:
        return t
    i = 0 if idioma == "en" else 1
    saida = None
    if t in EXATOS:
        saida = EXATOS[t][i]
    else:
        for regex, en, es in _PADROES:
            m = regex.match(t)
            if not m:
                continue
            modelo = en if idioma == "en" else es
            grupos = {str(k + 1): g or "" for k, g in enumerate(m.groups())}
            grupos.update({f"mes{k}": _mes(v, idioma, MESES) for k, v in grupos.items() if k.isdigit()})
            grupos.update({f"curto{k}": _mes(v, idioma, CURTOS) for k, v in list(grupos.items()) if k.isdigit()})
            # as partes variáveis também passam pelo catálogo (ex.: o tipo de desligamento no meio da frase)
            grupos.update({k: texto(v, idioma) if k.isdigit() and v in EXATOS else v for k, v in grupos.items()})
            saida = re.sub(r"\{(\w+)\}", lambda x: grupos.get(x.group(1), x.group(0)), modelo)
            break
    if saida is None:
        saida = t
    return _numeros_en(saida) if idioma == "en" else saida


def documento(doc: dict, idioma: str | None) -> dict:
    """O documento de relatório (nucleo/relatorios) com os textos no idioma; as contas não mudam."""
    if idioma not in ("en", "es"):
        return doc
    tr = lambda v: texto(v, idioma) if isinstance(v, str) else v
    secoes = []
    for s in doc.get("secoes", []):
        s2 = {**s, "titulo": tr(s.get("titulo"))}
        if s.get("tipo") == "tabela":
            s2["colunas"] = [tr(c) for c in s["colunas"]]
            s2["linhas"] = [[tr(c) for c in ln] for ln in s["linhas"]]
        elif s.get("tipo") == "lista":
            s2["itens"] = [tr(x) for x in s["itens"]]
        elif s.get("tipo") == "texto":
            s2["texto"] = tr(s["texto"])
        elif s.get("tipo") == "grafico":
            s2["rotulos"] = [tr(r) if r not in CURTOS["pt-BR"] else CURTOS[idioma][CURTOS["pt-BR"].index(r)] for r in s["rotulos"]]
        secoes.append(s2)
    return {**doc, "titulo": tr(doc.get("titulo")), "subtitulo": tr(doc.get("subtitulo")) if doc.get("subtitulo") else doc.get("subtitulo"),
            "resumo": [{**i, "rotulo": tr(i["rotulo"]), "valor": tr(i["valor"]),
                        "comparacoes": [{**c, "contra": tr(c["contra"])} for c in i.get("comparacoes") or []]} for i in doc.get("resumo", [])],
            "alertas": [tr(a) for a in doc.get("alertas") or []], "secoes": secoes,
            "como_calculamos": [tr(c) for c in doc.get("como_calculamos") or []]}


# o rodapé e as páginas fixas do PDF dos relatórios
PDF = {
    "pt-BR": {"gerado": "Gerado por {quem} em {d:%d/%m/%Y} às {d:%H:%M} · Código {codigo}", "pagina_de": " · página {n} de ",
              "gerado_simples": "Gerado por {quem} em {d:%d/%m/%Y às %H:%M} - código de verificação {codigo}",
              "rodape_doc": "Norte - {titulo} - código {codigo}", "pagina": " - página {n}", "como": "Como calculamos", "resumo": "Resumo",
              "alerta": "Alerta: {a}", "nada": "Nada neste período.", "slogan": "O aviso certo, para a comunidade certa",
              "barras": "Barras tracejadas: projeção pela média dos meses fechados.",
              "nota": "Só números agregados e o que está gravado: nenhum nome de cliente, número de UC, endereço ou coordenada. ",
              "nota_doc": "Confira o código de verificação na auditoria do Norte. ",
              "nota_completo": "Confira o código de verificação no Norte (a segunda via fica guardada e tem o mesmo SHA-256). "},
    "en": {"gerado": "Generated by {quem} on {d:%m/%d/%Y} at {d:%H:%M} · Code {codigo}", "pagina_de": " · page {n} of ",
           "gerado_simples": "Generated by {quem} on {d:%m/%d/%Y at %H:%M} - verification code {codigo}",
           "rodape_doc": "Norte - {titulo} - code {codigo}", "pagina": " - page {n}", "como": "How we calculate", "resumo": "Summary",
           "alerta": "Alert: {a}", "nada": "Nothing in this period.", "slogan": "The right notice, for the right community",
           "barras": "Dashed bars: projection by the average of the closed months.",
           "nota": "Only aggregated numbers and what is recorded: no customer name, UC number, address or coordinate. ",
           "nota_doc": "Check the verification code in the Norte audit. ",
           "nota_completo": "Check the verification code in Norte (the second copy is stored and has the same SHA-256). "},
    "es": {"gerado": "Generado por {quem} el {d:%d/%m/%Y} a las {d:%H:%M} · Código {codigo}", "pagina_de": " · página {n} de ",
           "gerado_simples": "Generado por {quem} el {d:%d/%m/%Y a las %H:%M} - código de verificación {codigo}",
           "rodape_doc": "Norte - {titulo} - código {codigo}", "pagina": " - página {n}", "como": "Cómo calculamos", "resumo": "Resumen",
           "alerta": "Alerta: {a}", "nada": "Nada en este período.", "slogan": "El aviso correcto, para la comunidad correcta",
           "barras": "Barras discontinuas: proyección por el promedio de los meses cerrados.",
           "nota": "Solo números agregados y lo que está registrado: ningún nombre de cliente, número de UC, dirección ni coordenada. ",
           "nota_doc": "Verifique el código de verificación en la auditoría de Norte. ",
           "nota_completo": "Verifique el código de verificación en Norte (la segunda copia queda guardada y tiene el mismo SHA-256). "},
}
AVISO_FICTICIO = {"en": ("Fictitious power grid and customers in this demonstration; real territory, addresses and communities "
                         "(IBGE, 2022 Census)."),
                  "es": ("Red eléctrica y clientes ficticios en esta demostración; territorio, direcciones y comunidades reales "
                         "(IBGE, Censo 2022).")}


def pdf(idioma: str | None, chave: str, **v) -> str:
    return PDF.get(idioma or PADRAO, PDF[PADRAO])[chave].format(**v)


def aviso_ficticio(idioma: str | None, pt: str) -> str:
    return AVISO_FICTICIO.get(idioma or PADRAO, pt)


def idioma_do_pedido(cabecalho: str | None) -> str:
    """O idioma da tela de quem pediu (cabeçalho X-Farol-Idioma); português se não vier ou não for conhecido."""
    return cabecalho if cabecalho in IDIOMAS else PADRAO
