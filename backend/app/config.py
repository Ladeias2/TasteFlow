"""Configuração da aplicação, lida de variáveis de ambiente (ou de um arquivo .env)."""
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


def _carregar_dotenv(caminho: Path) -> None:
    """Leitor mínimo de .env (chave=valor), sem dependência externa."""
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip())


_carregar_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class Settings:
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "3306"))
    db_user: str = os.getenv("DB_USER", "root")
    db_password: str = os.getenv("DB_PASSWORD", "")
    db_name: str = os.getenv("DB_NAME", "restaurante")

    # Preço do quilo aplicado quando a balança não informa
    preco_kg_semana: Decimal = Decimal(os.getenv("PRECO_KG_SEMANA", "89.90"))
    preco_kg_fim_semana: Decimal = Decimal(os.getenv("PRECO_KG_FIM_SEMANA", "99.90"))

    # Abaixo desta confiança média, a pesagem é marcada para revisão manual
    confianca_minima: float = float(os.getenv("CONFIANCA_MINIMA", "0.60"))

    # Brinde garantido para quem devolve o cartão de satisfação
    brinde_descricao: str = os.getenv("BRINDE_DESCRICAO", "Café expresso")
    brinde_custo: Decimal = Decimal(os.getenv("BRINDE_CUSTO", "1.50"))
    validade_cupom_dias: int = int(os.getenv("VALIDADE_CUPOM_DIAS", "7"))

    # Visão computacional (opcional)
    modelo_visao_path: str = os.getenv("MODELO_VISAO_PATH", "")
    versao_modelo: str = os.getenv("VERSAO_MODELO", "tasteflow-seg-demo")
    imgsz_visao: int = int(os.getenv("IMGSZ_VISAO", "320"))     # mesmo tamanho do treino
    pasta_fotos: str = os.getenv("PASTA_FOTOS", "storage")

    cors_origens: str = os.getenv("CORS_ORIGENS", "*")

    @property
    def database_url(self) -> str:
        return (f"mysql+pymysql://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4")


settings = Settings()
