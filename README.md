# Módulo Inteligente de Busca de Itens Perdidos

API de recuperação e ranqueamento textual de itens encontrados, desenvolvida como parte de um Trabalho de Conclusão de Curso. O usuário informa uma descrição livre do objeto perdido e recebe os itens ativos mais semelhantes.

## Linha de base

- normalização de texto em português;
- representação TF-IDF e similaridade do cosseno;
- similaridade normalizada de Levenshtein;
- combinação linear e ordenação dos candidatos;
- consulta somente de leitura aos itens com estado `ACTIVE`.

## Requisitos

- Python 3.11 ou superior;
- MySQL 8;
- banco `matching_development` com as tabelas `item` e `category`.

## Configuração

Crie e ative um ambiente virtual. Em seguida, instale o projeto com as dependências de desenvolvimento:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Os comandos utilizam diretamente o Python do ambiente virtual, sem depender da ativação de scripts do PowerShell.

Copie `.env.example` para `.env` e informe localmente a senha do usuário MySQL `matching_reader`. O arquivo `.env` é ignorado pelo Git.

```dotenv
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=matching_development
DB_USER=matching_reader
DB_PASSWORD=sua_senha_local
MATCH_METHOD=hybrid
MATCH_ALPHA=0.5
MATCH_BETA=0.5
```

`MATCH_METHOD` aceita `cosine`, `levenshtein` ou `hybrid`. No modo híbrido,
`MATCH_ALPHA` e `MATCH_BETA` definem os pesos das duas medidas e devem somar 1.
O índice TF-IDF é ajustado somente sobre os itens candidatos ativos, sem incluir
a consulta, e é reutilizado enquanto essa coleção e seus textos não mudarem.

## Execução

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

A documentação interativa fica disponível em `http://127.0.0.1:8000/docs`.

### Busca

`POST /matches/search`

```json
{
  "description": "Perdi um celular Samsung preto com capa azul na biblioteca",
  "top_k": 5
}
```

O endpoint consulta somente itens `ACTIVE`. Registros `RETURNED` e `ARCHIVED` não participam do ranking.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Os testes de unidade usam um repositório em memória e não modificam o MySQL.
