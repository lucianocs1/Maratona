"""Semente de demonstração: um mês e meio de histórico FICTÍCIO da empresa EMG para os relatórios da apresentação.

Cria (uma vez só; rodar de novo não duplica):
- 4 rádios de demonstração (e-mails @example.com, WhatsApp fictício), com alcance por município e por comunidade;
- cerca de 16 avisos nas últimas 6 semanas, cada um a partir das UCs FICTÍCIAS a jusante de uma chave da
  rede fictícia (simulacao/planilhas_teste.py), traduzidos e calculados pelo mesmo código da API;
- envios às rádios (e-mail, WhatsApp, cópia) com valor, economia e confirmação; um envio que falhou, um
  aviso sem envio, um cancelado e um que saiu fora do prazo, para os relatórios terem o que mostrar.
Os avisos e envios recebem datas passadas (é demonstração); a auditoria registra a semente com a data
de hoje ("semente de demonstração"). Nada de cliente real: rede, clientes e rádios são fictícios.

semear_ano() (Fase H) completa o ano, de janeiro até o começo do mês e meio acima, para os relatórios de custos,
comunidades e prazos: uns 3 avisos por mês, valores que variam de um envio para outro, uma rádio cara, um mês com
preço fora da curva (alerta de preço), a mesma comunidade 3 vezes em 30 dias (março e julho: repetição), alguns
fora do prazo, alguns envios não confirmados e um orçamento anual de rádio na configuração. Marca própria na
auditoria ("semente de demonstração (ano)"): rodar de novo não duplica.

semear_simulador() preenche o simulador de economia da EMG (R$ 160.000 a R$ 300.000, 100% cobrado por tempo, "valores
informados pela Energisa"), uma vez só e só se o Admin da empresa ainda não preencheu; a auditoria registra como da semente.

Uso (depois de uv run python -m comunidades.semente): uv run python -m comunidades.semente_demo (as duas)
"""

import sys
from datetime import datetime, timedelta
from decimal import Decimal

import geopandas as gpd

from . import config as C
from .api import app as api
from .api.comum import BRASILIA, config_empresa, segundos
from .banco import acesso as banco
from .banco import base_territorial as territorio
from .banco import radios as banco_radios
from .banco.conexao import conectar
from .nucleo import economia
from .nucleo.tipos_desligamento import TIPOS
from .simulacao import planilhas_teste

MARCA = "semente de demonstração"
MARCA_ANO = "semente de demonstração (ano)"
CARA = "Rádio Serra Alta FM (demonstração)"       # a rádio cara do ano (valor fechado alto)
MARCA_SIMULADOR = "semente de demonstração (simulador de economia)"
SIMULADOR_DEMO = {"gasto_min": Decimal("160000.00"), "gasto_max": Decimal("300000.00"), "pct_tempo": Decimal("100.00"),
                  "nota": "valores informados pela Energisa"}
ORCAMENTO_DEMO = 15000.0                            # orçamento anual de rádio da demonstração (R$), se não houver um
TIPOS_CICLO = ["manutencao_preventiva", "poda", "obra", "troca_equipamento", "corretiva_programada", "poda", "manutencao_preventiva"]


def _codigo(nome: str) -> str | None:
    return next((c for c, n, _, _ in territorio.contornos("EPSG:4674") if n == nome), None)


def _radios(empresa_id: int, admin_id: int) -> dict[str, int]:
    existentes = {r["nome"]: r["id"] for r in banco_radios.radios(empresa_id, so_ativas=False)}
    leo, cat = _codigo("Leopoldina"), _codigo("Cataguases")
    novas = [
        {"nome": "Rádio Leopoldina FM (demonstração)", "email": "leopoldina.fm@example.com", "whatsapp": "32999990001",
         "alcance": {"municipios": [leo], "comunidades": []}, "valor_padrao": Decimal("90.00"), "cobranca": "minuto"},
        {"nome": "Rádio Comunitária Piacatuba (demonstração)", "email": "piacatuba@example.com", "whatsapp": "32999990002",
         "alcance": {"municipios": [], "comunidades": [{"municipio": leo, "nome": "Piacatuba", "distrito": "Piacatuba"},
                                                       {"municipio": leo, "nome": "Graminha", "distrito": "Piacatuba"}]},
         "valor_padrao": Decimal("150.00"), "cobranca": "fechado"},
        {"nome": "Rádio Vale do Pomba (demonstração)", "email": "valedopomba@example.com", "whatsapp": None,
         "alcance": {"municipios": [m for m in (leo, cat) if m], "comunidades": []}, "valor_padrao": Decimal("250.00"), "cobranca": "fechado"},
        {"nome": "Rádio Tebas AM (demonstração)", "email": None, "whatsapp": "32999990004",
         "alcance": {"municipios": [], "comunidades": [{"municipio": leo, "nome": "Tebas", "distrito": "Tebas"},
                                                       {"municipio": leo, "nome": "Tomé Nogueira", "distrito": "Tebas"}]},
         "valor_padrao": Decimal("70.00"), "cobranca": "minuto"},
    ]
    for r in novas:
        if r["nome"] not in existentes:
            existentes[r["nome"]] = banco_radios.criar_radio(empresa_id, admin_id, {**r, "ativa": True})
    return existentes


def _chaves(n: int) -> list[str]:
    ch = gpd.read_file(C.SINTETICO / "chaves.gpkg", ignore_geometry=True)
    escolhidas = []
    for c in ch["COD_CHAVE"].tolist():
        try:
            t = planilhas_teste.planilha(c)
        except ValueError:
            continue
        if 60 <= len(t) <= 700:
            escolhidas.append(c)
        if len(escolhidas) >= n:
            break
    return escolhidas


def _aviso(u: dict, chave: str, tipo: str, data: str, horario: str) -> dict:
    t = planilhas_teste.planilha(chave)
    conteudo = t.to_csv(sep=";", decimal=",", index=False).encode("utf-8-sig")
    modelo = api._traduzir(conteudo, f"demonstracao_{chave}.csv", None, u)
    cfg = config_empresa(u["empresa_id"])
    resposta = api._resultado(modelo, data, horario, "pt-BR", cfg)
    motivo = TIPOS[tipo]
    api._mensagens(resposta["municipios"], cfg, data, horario, "pt-BR", motivo)
    return api._guardar(resposta, u, data, horario, "pt-BR", tipo, motivo, cfg)


def _envio(empresa_id: int, aviso_id: int, m: dict, rad: dict, canal: str, status: str, valor: Decimal, antigo: Decimal | None,
           quem: dict, enviado: datetime, k: int) -> int:
    """Um envio FICTÍCIO à rádio, com custo e economia pelo mesmo cálculo da API, na data passada."""
    texto = m.get("mensagem") or m["aviso"]
    seg, seg_hoje = segundos(texto), (m.get("hoje") or {}).get("segundos")
    eco = economia.calcular(rad["cobranca"], valor, seg, seg_hoje, antigo)
    envio_id = banco_radios.criar_envio({
        "empresa_id": empresa_id, "aviso_id": aviso_id, "municipio": m["codigo_ibge"], "municipio_nome": m["nome"],
        "radio_id": rad["id"], "radio_nome": rad["nome"], "canal": canal,
        "destino": rad["email"] if canal == "email" else rad["whatsapp"] if canal == "whatsapp" else "", "texto": texto,
        "valor": valor, "cobranca": rad["cobranca"], "custo": eco["custo"], "custo_antigo": antigo,
        "economia": eco["economia"], "economia_tipo": eco["economia_tipo"], "segundos": seg, "segundos_hoje": seg_hoje,
        "tempo_economizado": eco["tempo_economizado"], "status": status, "criado_por": quem["id"], "criado_por_nome": quem["nome"]})
    with conectar() as c:
        c.execute("UPDATE envio SET criado_em = %s, confirmado_em = %s WHERE id = %s",
                  (enviado, enviado + timedelta(hours=2, minutes=13 * k) if status == "confirmado" else None, envio_id))
    return envio_id


def semear_demo(n_avisos: int = 16) -> dict:
    emp = banco.empresa_por_sigla("EMG")
    if not emp:
        raise SystemExit("Rode antes: uv run python -m comunidades.semente")
    with conectar() as c:
        if c.execute("SELECT 1 FROM registro WHERE acao = %s AND empresa_id = %s", (MARCA, emp["id"])).fetchone():
            return {"criados": 0, "motivo": "a semente de demonstração já foi aplicada nesta empresa"}
    op = banco.usuario_por_email("operador@emg.example")
    adm = banco.usuario_por_email("admin@emg.example")
    radios = _radios(emp["id"], adm["id"])
    agora = datetime.now(BRASILIA).replace(second=0, microsecond=0)
    criados, envios = 0, 0
    for i, chave in enumerate(_chaves(n_avisos)):
        quem = adm if i % 5 == 4 else op
        u = {**quem, "empresa_nome": emp["nome"]}
        gerado = agora - timedelta(days=42 - i * 2.6, hours=(i * 7) % 9)
        antecedencia = 2 if i == 6 else 9          # o 7º sai em cima da hora: fora do prazo
        desl = gerado + timedelta(days=antecedencia)
        tipo = TIPOS_CICLO[i % len(TIPOS_CICLO)]
        r = _aviso(u, chave, tipo, f"{desl:%d/%m}", ["8h às 14h", "9h às 15h", "8h às 12h", "13h às 17h"][i % 4])
        with conectar() as c:
            c.execute("UPDATE aviso SET criado_em = %s WHERE id = %s", (gerado, r["id"]))
        criados += 1
        if i == 9:                                    # um sem envio registrado
            continue
        if i == 12:                                   # um cancelado (sem envio)
            banco.cancelar_aviso(r["id"], emp["id"])
            banco.registrar("cancelou o aviso", f"aviso {r['id']}: chuva forte prevista ({MARCA})", op["id"], emp["id"])
            continue
        for m in r["municipios"]:
            alvo = [radios["Rádio Leopoldina FM (demonstração)"]] if m["nome"] == "Leopoldina" else []
            if m["nome"] == "Leopoldina" and i % 3 == 0:
                alvo.append(radios["Rádio Vale do Pomba (demonstração)"])
            if m["nome"] == "Leopoldina" and any(c["distrito"] in ("Piacatuba", "Tebas") for c in m["comunidades"]) and i % 2 == 1:
                alvo.append(radios["Rádio Comunitária Piacatuba (demonstração)"])
            for k, radio_id in enumerate(alvo):
                rad = banco_radios.radio(radio_id, emp["id"])
                canal = "email" if rad["email"] and k == 0 else "whatsapp" if rad["whatsapp"] else "copia"
                status = "falhou" if i == 3 and k == 0 else "confirmado" if canal == "email" else "enviado"
                antigo = Decimal("420.00") if rad["cobranca"] == "fechado" and i % 2 == 0 else None
                _envio(emp["id"], r["id"], m, rad, canal, status, rad["valor_padrao"], antigo, quem, gerado + timedelta(minutes=20 + 7 * k), k)
                envios += 1
    banco.registrar(MARCA, f"{criados} avisos fictícios, {envios} envios fictícios e {len(radios)} rádios de demonstração", adm["id"], emp["id"])
    return {"criados": criados, "envios": envios, "radios": len(radios)}


def semear_ano() -> dict:
    """O ano FICTÍCIO, de janeiro até 44 dias atrás (onde começa a semear_demo). Não duplica."""
    emp = banco.empresa_por_sigla("EMG")
    if not emp:
        raise SystemExit("Rode antes: uv run python -m comunidades.semente")
    with conectar() as c:
        if c.execute("SELECT 1 FROM registro WHERE acao = %s AND empresa_id = %s", (MARCA_ANO, emp["id"])).fetchone():
            return {"criados": 0, "motivo": "a semente do ano já foi aplicada nesta empresa"}
    op = banco.usuario_por_email("operador@emg.example")
    adm = banco.usuario_por_email("admin@emg.example")
    radios = _radios(emp["id"], adm["id"])
    if CARA not in radios:
        radios[CARA] = banco_radios.criar_radio(emp["id"], adm["id"], {
            "nome": CARA, "email": "serraalta@example.com", "whatsapp": None, "alcance": {"municipios": [_codigo("Leopoldina")], "comunidades": []},
            "valor_padrao": Decimal("480.00"), "cobranca": "fechado", "ativa": True})
    cfg = config_empresa(emp["id"])
    if cfg["orcamento_radio"] is None:
        banco_radios.salvar_config(emp["id"], adm["id"], {**cfg, "orcamento_radio": ORCAMENTO_DEMO})
    agora = datetime.now(BRASILIA).replace(second=0, microsecond=0)
    limite = agora - timedelta(days=44)
    pool = _chaves(8)
    plano, d, n = [], datetime(agora.year, 1, 6, 9, 0, tzinfo=BRASILIA), 0
    while d < limite:                                          # uns 3 por mês, de 9 a 14 dias entre um e outro
        plano.append((d, pool[n % len(pool)]))
        n += 1
        d += timedelta(days=9 + (n * 5) % 6, hours=(n * 3) % 7)
    for mes in (3, 7):                                         # repetição: a mesma chave 3 vezes em 30 dias
        for dia in (4, 14, 25):
            quando = datetime(agora.year, mes, dia, 10, 0, tzinfo=BRASILIA)
            if quando < limite:
                plano.append((quando, pool[0]))
    plano.sort()
    criados, envios = 0, 0
    for i, (gerado, chave) in enumerate(plano):
        quem = adm if i % 4 == 3 else op
        u = {**quem, "empresa_nome": emp["nome"]}
        antecedencia = 2 if i % 6 == 2 else 8 + i % 5             # alguns em cima da hora: fora do prazo
        desl = gerado + timedelta(days=antecedencia)
        tipo = TIPOS_CICLO[(i + 3) % len(TIPOS_CICLO)]
        r = _aviso(u, chave, tipo, f"{desl:%d/%m}", ["8h às 14h", "9h às 15h", "8h às 12h", "13h às 17h", "7h às 16h"][i % 5])
        with conectar() as c:
            c.execute("UPDATE aviso SET criado_em = %s WHERE id = %s", (gerado, r["id"]))
        criados += 1
        if i == 11:                                            # um cancelado
            banco.cancelar_aviso(r["id"], emp["id"])
            banco.registrar("cancelou o aviso", f"aviso {r['id']}: obra adiada pela prefeitura ({MARCA_ANO})", op["id"], emp["id"])
            continue
        if i == 17:                                            # um sem envio registrado
            continue
        for m in r["municipios"]:
            if m["nome"] != "Leopoldina":
                continue
            alvo = ["Rádio Leopoldina FM (demonstração)"] + (["Rádio Vale do Pomba (demonstração)"] if i % 3 == 0 else []) \
                + ([CARA] if i % 4 == 1 else []) \
                + (["Rádio Comunitária Piacatuba (demonstração)"] if any(c["distrito"] in ("Piacatuba", "Tebas") for c in m["comunidades"]) else [])
            for k, nome in enumerate(alvo):
                rad = banco_radios.radio(radios[nome], emp["id"])
                canal = "email" if rad["email"] and k != 2 else "whatsapp" if rad["whatsapp"] else "copia"
                variacao = Decimal(str(1 + ((i + k) % 5 - 2) * 0.04))  # valores de -8% a +8% em volta do padrão
                if gerado.month == 7 and nome == "Rádio Vale do Pomba (demonstração)":
                    variacao = Decimal("1.6")                      # julho: preço fora da curva (alerta de preço)
                valor = (rad["valor_padrao"] * variacao).quantize(Decimal("0.01"))
                status = "confirmado" if canal == "email" and (i + k) % 5 != 2 else "entregue" if canal == "email" else "enviado"
                antigo = Decimal("420.00") if rad["cobranca"] == "fechado" and i % 2 == 0 else None
                _envio(emp["id"], r["id"], m, rad, canal, status, valor, antigo, quem, gerado + timedelta(minutes=25 + 9 * k), k)
                envios += 1
    banco.registrar(MARCA_ANO, f"{criados} avisos fictícios de janeiro a {limite:%d/%m}, {envios} envios fictícios, rádio cara ({CARA})"
                    f" e orçamento de rádio de demonstração", adm["id"], emp["id"])
    return {"criados": criados, "envios": envios, "radios": len(radios)}


# ---------- A segunda empresa de demonstração: Distribuidora Exemplo (DEX), no Mato Grosso do Sul ----------
# Fictícia: domínio reservado para teste (exemplo.example), sem CNPJ, área em alguns municípios do MS (o mapa das
# empresas mostra duas empresas em estados diferentes). Nenhum dado de empresa real.
EXEMPLO = {"nome": "Distribuidora Exemplo (demonstração)", "sigla": "DEX", "dominio": "exemplo.example"}
AREA_EXEMPLO = ["5001102", "5002704", "5003207", "5003702", "5005707", "5006606", "5008305"]   # Aquidauana, Campo Grande,
# Corumbá, Dourados, Naviraí, Ponta Porã e Três Lagoas
REAIS = ("energisa.com.br",)   # domínios reais que já apareceram em cadastro de teste: viram a empresa fictícia


def empresa_exemplo() -> dict:
    """Garante a DEX com a área no MS. Uma empresa de teste com domínio real (ex.: a "Energisa" cadastrada à mão) vira a
    DEX: nome, sigla, domínio e CNPJ trocados e os e-mails dos usuários passados para o domínio fictício; cada troca
    vai para a auditoria com o antes e o depois (nada da auditoria é apagado)."""
    from .senhas import hash_senha, senha_temporaria
    feito = {"empresa": None, "trocada": None, "senha_admin": None}
    e = banco.empresa_por_sigla(EXEMPLO["sigla"])
    if not e:
        with conectar() as c:
            real = c.execute("SELECT id FROM empresa WHERE dominio = ANY(%s) ORDER BY id LIMIT 1", (list(REAIS),)).fetchone()
        if real:
            antes = banco.empresa(real[0])
            with conectar() as c:
                c.execute("UPDATE empresa SET nome = %s, sigla = %s, dominio = %s, cnpj = NULL WHERE id = %s",
                          (EXEMPLO["nome"], EXEMPLO["sigla"], EXEMPLO["dominio"], real[0]))
                usuarios = c.execute("SELECT id, email FROM usuario WHERE empresa_id = %s", (real[0],)).fetchall()
                for uid, email in usuarios:
                    c.execute("UPDATE usuario SET email = %s WHERE id = %s", (email.split("@")[0] + "@" + EXEMPLO["dominio"], uid))
            banco.registrar("alterou empresa", f"{antes['nome']} ({antes['sigla']}) → {EXEMPLO['nome']} ({EXEMPLO['sigla']}): domínio "
                            f"{antes['dominio']} → {EXEMPLO['dominio']}, CNPJ removido (empresa de teste com dados reais trocada pela "
                            "fictícia da demonstração)", None, real[0])
            for uid, email in usuarios:
                banco.registrar("alterou usuário", f"e-mail {email} → {email.split('@')[0]}@{EXEMPLO['dominio']} (domínio fictício)", None, real[0])
            feito["trocada"] = f"{antes['sigla']} → {EXEMPLO['sigla']}"
        else:
            temporaria = senha_temporaria()
            banco.criar_empresa_com_admin(EXEMPLO["nome"], EXEMPLO["sigla"], EXEMPLO["dominio"], None, "admin@exemplo.example",
                                          "Admin da Exemplo", hash_senha(temporaria), "semente de demonstração")
            banco.registrar("semente: criou a empresa", f"{EXEMPLO['nome']} e o primeiro admin", None, banco.empresa_por_sigla("DEX")["id"])
            feito["senha_admin"] = temporaria
        e = banco.empresa_por_sigla(EXEMPLO["sigla"])
    if not banco.area(e["id"]):
        banco.salvar_area(e["id"], AREA_EXEMPLO, "área de atuação: carga da demonstração",
                          f"{EXEMPLO['sigla']}: {len(AREA_EXEMPLO)} municípios do MS (fictício)", None)
    feito["empresa"] = {"sigla": e["sigla"], "municipios": len(banco.area(e["id"]))}
    return feito


def semear_simulador() -> dict:
    """O gasto mensal com rádio da EMG no simulador de economia (R$ 160.000 a R$ 300.000, 100% por tempo), para os cartões
    aparecerem completos na apresentação. Uma vez só; se o Admin da empresa já preencheu, não mexe. Na auditoria, como da semente."""
    emp = banco.empresa_por_sigla("EMG")
    if not emp:
        raise SystemExit("Rode antes: uv run python -m comunidades.semente")
    with conectar() as c:
        if c.execute("SELECT 1 FROM registro WHERE acao = %s AND empresa_id = %s", (MARCA_SIMULADOR, emp["id"])).fetchone():
            return {"simulador": "já aplicado"}
    if config_empresa(emp["id"])["simulador"]["gasto_min"] is not None:
        return {"simulador": "já preenchido pelo Admin da empresa"}
    v = SIMULADOR_DEMO
    banco_radios.salvar_simulador(emp["id"], None, v["gasto_min"], v["gasto_max"], v["pct_tempo"], v["nota"])
    banco.registrar(MARCA_SIMULADOR, f"gasto mensal (mínimo): — → {v['gasto_min']}; gasto mensal (máximo): — → {v['gasto_max']}; "
                    f"% cobrado por tempo: 100.00 → {v['pct_tempo']}; origem dos valores: — → {v['nota']}", None, emp["id"])
    return {"simulador": f"{v['gasto_min']} a {v['gasto_max']}, {v['pct_tempo']}% por tempo"}


if __name__ == "__main__":
    print(semear_demo(int(sys.argv[1]) if len(sys.argv) > 1 else 16))
    print(semear_ano())
    print(semear_simulador())
    print(empresa_exemplo())
