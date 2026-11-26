# IA — Visão computacional do TasteFlow

Modelo de **segmentação de alimentos** (YOLOv8-seg) que identifica o que há no prato a partir da foto tirada na balança. A área de cada alimento vira um **percentual do prato**. A API combina esse percentual com o **peso real** da balança e o custo/kg de cada ingrediente para calcular o custo do prato (ICC) e o Custo Real por Cliente (CRC).

```
foto do prato ─► YOLOv8-seg ─► máscaras por alimento ─► % de área ─► POST /pesagens
                                                                     │
                     peso da balança × % × custo/kg  ◄───────────────┘  (banco: vw_custo_pesagem)
```

> **Sobre o modelo incluído.** `modelos/tasteflow-seg-demo.pt` foi treinado com **pratos sintéticos**, montados com texturas recortadas de 3 fotos reais. Ele serve para validar o pipeline de ponta a ponta (treino → avaliação → API). **Não serve para uso real.** Para o restaurante é preciso treinar com fotos reais anotadas (seção "Modelo de produção").

## Estrutura

```
ia/
├── config/
│   ├── dataset.yaml          classes (= ingrediente.rotulo_ia) e pastas do dataset
│   ├── treino.yaml           hiperparâmetros: perfis "producao" e "demonstracao"
│   ├── texturas.yaml         recortes de fotos reais usados nos pratos sintéticos
│   ├── sintetico.yaml        parâmetros do gerador de pratos sintéticos
│   └── estacao_balanca.yaml  câmera, balança (serial), modelo e API da estação
├── scripts/
│   ├── comum.py                  composição do prato a partir das máscaras (mesma regra da API)
│   ├── extrair_texturas.py       recorta texturas reais de alimentos e fundos
│   ├── gerar_dataset_sintetico.py  gera pratos sintéticos já anotados
│   ├── coco_para_yolo.py         converte fotos reais anotadas (COCO) para YOLO-seg
│   ├── treinar.py                treina e salva o melhor peso em modelos/
│   ├── avaliar.py                mAP das máscaras + erro da composição do prato
│   ├── inferir.py                roda o modelo em fotos, salva imagem anotada, envia à API
│   ├── exportar.py               exporta para ONNX (estação sem GPU)
│   ├── estacao_balanca.py        estação completa: comanda → balança → câmera → API
│   └── sincronizar_classes.py    alinha dataset.yaml com os ingredientes do banco
├── modelos/
│   └── tasteflow-seg-demo.pt     modelo de demonstração (6,8 MB)
├── fotos_referencia/             fotos para texturas (não vão para o Git)
└── dados/                        dataset, texturas e saídas (não vão para o Git)
```

## Instalação

```bash
cd ia
python -m venv .venv
.venv\Scripts\Activate.ps1        # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt   # instala o PyTorch junto com o Ultralytics
```

Todos os comandos abaixo são executados de dentro da pasta `ia/`.

## Reproduzir o modelo de demonstração

```bash
python scripts/extrair_texturas.py           # 23 recortes de 7 alimentos + fundos
python scripts/gerar_dataset_sintetico.py    # 360 treino / 80 validação / 40 teste (~1 min)
python scripts/treinar.py --perfil demonstracao   # ~35 min em CPU com 2 núcleos
python scripts/avaliar.py                    # métricas no conjunto de teste
python scripts/inferir.py fotos_referencia/prato3.png   # testa numa foto real
```

As fotos de referência não vão para o repositório. Coloque as suas em `fotos_referencia/` e ajuste as caixas em `config/texturas.yaml`.

## Modelo de produção (fotos reais)

1. **Coleta:** fotografe os pratos de cima, **na própria estação** (mesma câmera, altura e iluminação). Para começar, umas **300 a 500 fotos**, variando horários e cardápios. Cada alimento deve aparecer em pelo menos 50 fotos.
2. **Anotação:** no [CVAT](https://www.cvat.ai/) ou no Label Studio, desenhe **polígonos** em cada porção, com os nomes exatos de `config/dataset.yaml`. Exporte em **COCO 1.0**.
3. **Conversão:**
   ```bash
   python scripts/coco_para_yolo.py --coco anotacoes.json --imagens fotos/
   ```
4. **Treino** (GPU recomendada; o Google Colab gratuito serve):
   ```bash
   python scripts/treinar.py --perfil producao
   ```
   Opcional: pré-treine com o dataset sintético e depois ajuste com as fotos reais. Isso ajuda quando há poucas fotos.
5. **Avaliação:** `python scripts/avaliar.py --modelo modelos/tasteflow-seg.pt --imgsz 640`
6. **Implantação:** aponte a API (`MODELO_VISAO_PATH` no `.env` do backend) ou a estação (`config/estacao_balanca.yaml`) para o novo `.pt`.

Quando um ingrediente for cadastrado no banco, rode `python scripts/sincronizar_classes.py`. Ele acrescenta a classe ao fim da lista, sem mudar o número das classes existentes, e o modelo precisa ser retreinado.

## Estação da balança

```bash
# teste sem câmera e sem balança (pede o peso pelo teclado; API rodando em localhost:8000)
python scripts/estacao_balanca.py --imagem fotos_referencia/prato3.png --uma-vez
```

Na operação real, em `config/estacao_balanca.yaml`:
- `balanca.modo: serial`, com a porta e a `regex_peso` do protocolo da balança (a maioria envia o peso em texto, como `ST,GS,+0.852kg`);
- `camera.indice` da câmera USB;
- `recorte_prato`, se a câmera enxergar além do prato.

O leitor de código de barras da comanda funciona como teclado.

Para rodar sem PyTorch na estação: `python scripts/exportar.py` gera um `.onnx`.

## Como a composição é calculada

1. O modelo devolve uma máscara por porção identificada.
2. Se duas máscaras cobrem o mesmo pixel, ele fica com a de maior confiança, para nunca contar o mesmo pixel duas vezes.
3. As áreas são somadas por alimento e divididas pela área total de comida, o que dá o percentual.
4. A confiança de cada alimento é a média das confianças ponderada pela área.

A regra está em `scripts/comum.py` e em `backend/app/services/visao.py`.

**Limitação conhecida:** área não é massa. Alimentos densos ou empilhados (carne, feijão com caldo) pesam mais do que a área sugere. O próximo passo é calibrar um fator de densidade por alimento, pesando porções conhecidas.
