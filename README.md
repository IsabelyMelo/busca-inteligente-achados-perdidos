# Módulo Inteligente de Busca de Itens Perdidos

API de recuperação e ranqueamento textual de itens encontrados, desenvolvida como parte de um Trabalho de Conclusão de Curso. O usuário informa uma descrição livre do objeto perdido e recebe os itens ativos mais semelhantes.

## Linha de base

- normalização de texto em português;
- representação TF-IDF e similaridade do cosseno;
- similaridade normalizada de Levenshtein;
- combinação linear e ordenação dos candidatos;
- consulta somente de leitura aos itens com estado `ACTIVE`.

O texto de recuperação concatena nome, descrição e local do item. A categoria
permanece como metadado; a comparação controlada no piloto de desenvolvimento
está registrada em `evaluation/README.md` e no resumo exportado pelo avaliador.

## Requisitos

- Python 3.11 ou superior;
- MySQL 8;
- schema sintético de desenvolvimento `matching_development` com as tabelas `item` e `category`.

## Configuração

Crie e ative um ambiente virtual. Em seguida, instale o projeto com as dependências de desenvolvimento:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Os comandos utilizam diretamente o Python do ambiente virtual, sem depender da ativação de scripts do PowerShell.

Copie `.env.example` para `.env` e informe localmente a senha do usuário MySQL `matching_reader` e uma credencial aleatória de serviço com pelo menos 32 caracteres. O arquivo `.env` é ignorado pelo Git. Gere a credencial, por exemplo, com `python -c "import secrets; print(secrets.token_urlsafe(32))"` e guarde o valor fora do repositório.

```dotenv
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=matching_development
DB_USER=matching_reader
DB_PASSWORD=sua_senha_local
SERVICE_API_KEY=cole_aqui_a_credencial_aleatoria_gerada
RATE_LIMIT_PER_MINUTE=60
MATCH_METHOD=hybrid
MATCH_ALPHA=0.5
MATCH_BETA=0.5
```

`MATCH_METHOD` aceita `cosine`, `levenshtein` ou `hybrid`. No modo híbrido,
`MATCH_ALPHA` e `MATCH_BETA` definem os pesos das duas medidas e devem somar 1.
O índice TF-IDF é ajustado somente sobre os itens candidatos ativos, sem incluir
a consulta, e é reutilizado enquanto essa coleção e seus textos não mudarem.

A API recusa iniciar sem `SERVICE_API_KEY`. O cabeçalho `X-Service-Key` protege
`POST /matches/search`; a chave deve ficar no ambiente do serviço consumidor,
sem exposição a navegador ou usuário final. A credencial identifica um único
consumidor de serviço, não pessoas. Ausência ou valor inválido retornam 401;
excesso de requisições retorna 429 com `Retry-After`; falha interna de busca
retorna 503 sem detalhes do banco. Requisições inválidas retornam 422 sem ecoar
o texto enviado. O limite padrão é de 60 buscas autorizadas por janela móvel de
60 segundos, compartilhado por essa credencial em uma única instância. Uma
reinicialização ou hibernação zera a contagem; várias instâncias teriam
contadores independentes. Assim, o limite reduz abuso ocasional, mas não é uma
quota durável nem proteção distribuída.

Os logs de auditoria registram data/hora UTC, identificador `service` ou
`anonymous`, rota permitida, status e duração. Não incluem descrição, chave,
endereço do banco nem SQL. O identificador `service` representa a credencial
única, sem identificar usuários finais. A resposta de busca contém os campos do
item necessários para apresentação; publique somente a base sintética aprovada.

Para a opção Render Free + Aiven MySQL Free, configure as mesmas variáveis no
Render e monte o certificado CA da Aiven como arquivo secreto. Defina
`DB_SSL_CA` com o caminho absoluto desse arquivo: a conexão PyMySQL passa a
exigir certificado válido e identidade do host. Em produção, use um usuário
MySQL com `SELECT` restrito às tabelas necessárias; a aplicação não executa
escritas. A conexão TLS real, privilégios e CA inválida devem ser validados em
E09 antes da publicação. Nunca inclua o CA, a chave ou a senha no Git.

`matching_development` foi criado para esta aplicação e é separado do banco institucional original. Em 15/10/2026, recebeu os 1.000 itens encontrados aprovados, com IDs 1001–2000 e estado `ACTIVE`. As consultas rotuladas permanecem nos JSONL de `evaluation/final/`; a divisão 700/300 existe apenas no manifesto e no avaliador. A carga e sua conferência estão descritas em `evaluation/final/README.md`.

## Execução

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

A documentação interativa fica disponível em `http://127.0.0.1:8000/docs`.
`GET /health` responde `{"status":"ok"}` sem consultar o banco. O Render
aceita esse caminho como health check HTTP; ele verifica a resposta do processo,
não a disponibilidade da busca. Não há `/ready`, pois a hospedagem não exige
outro endpoint. Confira a busca separadamente após iniciar ou reativar o serviço.

### Busca

`POST /matches/search`

Envie `X-Service-Key` no cabeçalho, por exemplo:

```powershell
$headers = @{ "X-Service-Key" = $env:SERVICE_API_KEY }
$body = @{ description = "Perdi um celular Samsung preto com capa azul na biblioteca"; top_k = 5 } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/matches/search -Method Post -Headers $headers -ContentType application/json -Body $body
```

```json
{
  "description": "Perdi um celular Samsung preto com capa azul na biblioteca",
  "top_k": 5
}
```

O endpoint consulta somente itens `ACTIVE`. Registros `RETURNED` e `ARCHIVED` não participam do ranking.
O resultado é uma lista de sugestões ordenadas; não confirma automaticamente
uma correspondência. O limiar 0,6 pertence somente à classificação experimental
por par e não filtra a resposta da API. Mesmo uma descrição sem correspondência
rotulada pode receber `top_k` candidatos.

### Transporte e limite na hospedagem prevista

O [Render fornece TLS e redireciona HTTP para HTTPS](https://render.com/docs/web-services)
na borda do Web Service; a aplicação recebe tráfego HTTP após a terminação TLS.
O [plano Free permite uma instância e hiberna após 15 minutos sem tráfego](https://render.com/docs/free),
com retorno que pode levar cerca de um minuto. Por isso o limite fica no
processo único, sem gateway próprio. O HTTPS do domínio implantado e o limite
observado externamente ainda exigem teste em E09. O tráfego API–Aiven deve ser
validado separadamente com o CA da Aiven.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Os testes de unidade usam um repositório em memória e não modificam o MySQL.
Para repetir a verificação manual local, sem acessar o banco, execute:

```powershell
.\.venv\Scripts\python.exe -m scripts.manual_security_check
```

Ela exerce busca válida, credenciais ausente e inválida, limite, falha simulada
do banco, `/health` e inspeção dos logs. Após configurar Render e Aiven em E09,
repita por HTTPS contra a URL publicada e confira também certificado TLS,
permissões `SELECT` e comportamento após hibernação. A latência HTTP medida
localmente com catálogo em memória na avaliação não representa o tempo de busca
dos 1.000 itens via MySQL remoto.
