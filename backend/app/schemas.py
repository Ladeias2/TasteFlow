"""Contratos de entrada da API (Pydantic v2).

As faixas válidas repetem os CHECK constraints do banco, para que o erro seja
devolvido de forma amigável antes mesmo de chegar ao MySQL.
"""
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator



# ---------------------------------------------------------------- cadastros
class GarcomIn(BaseModel):
    nome: str = Field(min_length=2, max_length=100)
    ativo: bool = True


class MesaIn(BaseModel):
    numero_mesa: int = Field(gt=0)
    capacidade: int = Field(default=4, gt=0)


class Categoria(str, Enum):
    guarnicao = "guarnicao"
    salada = "salada"
    legume = "legume"
    massa = "massa"
    carne = "carne"
    frutos_mar = "frutos_mar"
    sobremesa = "sobremesa"


class Estacao(str, Enum):
    buffet = "buffet"
    churrasqueira = "churrasqueira"


class IngredienteIn(BaseModel):
    nome_ingrediente: str = Field(min_length=2, max_length=80)
    rotulo_ia: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$")
    categoria: Categoria
    estacao: Estacao = Estacao.buffet
    custo_kg: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


class IngredienteUpdate(BaseModel):
    custo_kg: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    ativo: bool | None = None


# ---------------------------------------------------------------- comandas
class ComandaIn(BaseModel):
    id_comanda_aleatoria: str | None = Field(
        default=None, max_length=50,
        description="Código já impresso no cartão; se omitido a API gera um aleatório")


class PedidoIn(BaseModel):
    id_comanda: str = Field(max_length=50)
    id_garcom: int | None = None
    item_consumo: str = Field(min_length=1, max_length=150)
    quantidade: int = Field(default=1, gt=0)
    valor_unitario: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


# ---------------------------------------------------------------- IA / composição
class ItemComposicao(BaseModel):
    """Um alimento identificado pelo modelo de visão computacional."""
    rotulo: str = Field(description="Classe do modelo; deve existir em ingrediente.rotulo_ia")
    percentual: float = Field(gt=0, le=100, description="Fração estimada do prato (área segmentada)")
    confianca: float | None = Field(default=None, ge=0, le=1)


def _rotulos_unicos(itens: list[ItemComposicao]) -> list[ItemComposicao]:
    rotulos = [i.rotulo for i in itens]
    if len(set(rotulos)) != len(rotulos):
        raise ValueError("Rótulos repetidos na composição.")
    return itens


class PesagemIn(BaseModel):
    """Payload enviado pela estação balança + câmera (POST /pesagens)."""
    id_comanda: str = Field(max_length=50)
    peso_gramas: int = Field(gt=0, le=5000)
    preco_kg_aplicado: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    url_foto: str | None = Field(default=None, max_length=255)
    versao_modelo: str | None = Field(default=None, max_length=30)
    itens: list[ItemComposicao] = Field(default_factory=list,
                                        description="Saída da IA; pode vir vazia (classificação posterior)")

    @field_validator("itens")
    @classmethod
    def _sem_repetidos(cls, v: list[ItemComposicao]) -> list[ItemComposicao]:
        return _rotulos_unicos(v)


class ComposicaoManualIn(BaseModel):
    """Correção feita por um funcionário quando a IA tem baixa confiança."""
    itens: list[ItemComposicao] = Field(min_length=1)

    @field_validator("itens")
    @classmethod
    def _sem_repetidos(cls, v: list[ItemComposicao]) -> list[ItemComposicao]:
        return _rotulos_unicos(v)


# ---------------------------------------------------------------- fluxo
class TipoEvento(str, Enum):
    chegada_churrasqueira = "chegada_churrasqueira"
    atendido_churrasqueira = "atendido_churrasqueira"
    chamado_garcom = "chamado_garcom"
    saida = "saida"


class OrigemEvento(str, Enum):
    comanda = "comanda"      # leitura da própria comanda eletrônica
    leitor = "leitor"        # leitor na churrasqueira
    sensor = "sensor"        # porta / catraca
    botao = "botao"          # botão de chamada na mesa
    manual = "manual"


class EventoIn(BaseModel):
    id_comanda: str = Field(max_length=50)
    tipo_evento: TipoEvento
    origem_evento: OrigemEvento = OrigemEvento.comanda
    id_garcom: int | None = None
    data_hora_evento: datetime | None = Field(
        default=None, description="Se omitido, usa o horário do servidor")


# ---------------------------------------------------------------- mesas
class OcuparIn(BaseModel):
    """Garçom toca na mesa no tablet quando o grupo senta."""
    qtd_pessoas: int = Field(default=1, gt=0, le=20)
    id_garcom: int | None = None
    comandas: list[str] = Field(default_factory=list,
                                description="Opcional: comandas do grupo, se o garçom quiser vincular")


class AvancarIn(BaseModel):
    id_garcom: int | None = Field(default=None, description="Funcionário que tocou na mesa")


class VincularIn(BaseModel):
    id_comanda: str = Field(max_length=50)


# ---------------------------------------------------------------- satisfação
NotaCartao = Field(ge=0, le=5, description="0 = insatisfeito, 5 = satisfeito")


class Recomendaria(str, Enum):
    sim = "sim"
    talvez = "talvez"
    nao = "nao"


class AvaliacaoIn(BaseModel):
    """Cartão raspadinha lançado pelo caixa."""
    codigo_cartao: str = Field(max_length=12, description="Código de barras impresso no cartão")
    id_comanda: str = Field(max_length=50)
    nota_comida: int = NotaCartao
    nota_ambiente: int = NotaCartao
    nota_atendimento: int = NotaCartao
    recomendaria: Recomendaria
    comentario: str | None = Field(default=None, max_length=500)


class LoteCartoesIn(BaseModel):
    quantidade: int = Field(gt=0, le=2000)
    lote: str | None = Field(default=None, max_length=20, description="Se omitido: L<AAAAMMDD>")


class ResgateIn(BaseModel):
    id_comanda: str = Field(max_length=50, description="Comanda da visita em que o brinde é usado")


# ---------------------------------------------------------------- sobras
class ItemSobra(BaseModel):
    rotulo: str
    peso_gramas: int | None = Field(default=None, ge=0)
    percentual: float | None = Field(default=None, gt=0, le=100)
    confianca: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _um_dos_dois(self):
        if (self.peso_gramas is None) == (self.percentual is None):
            raise ValueError("Informe peso_gramas OU percentual para cada item.")
        return self


class SobraIn(BaseModel):
    id_pesagem: int
    peso_sobra_gramas: int = Field(ge=0)
    url_foto: str | None = Field(default=None, max_length=255)
    itens: list[ItemSobra] = Field(default_factory=list)


class Turno(str, Enum):
    almoco = "almoco"
    jantar = "jantar"


class ProducaoIn(BaseModel):
    data_producao: date
    turno: Turno = Turno.almoco
    rotulo: str
    peso_produzido_gramas: int = Field(ge=0)
    peso_descartado_gramas: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _descarte_menor(self):
        if self.peso_descartado_gramas > self.peso_produzido_gramas:
            raise ValueError("O descarte não pode ser maior que a produção.")
        return self
