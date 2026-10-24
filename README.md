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

O arquivo `.python-version` seleciona Python 3.12 no Render. A avaliação final
foi executada com Python 3.12.14; o Render usa o patch mais recente da série 3.12.

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
`DB_SSL_CA=/etc/secrets/aiven-ca.pem` e `DB_REQUIRE_TLS=true`: a conexão
PyMySQL passa a exigir certificado válido e identidade do host. O serviço
recusa iniciar se o CA faltar ou for inválido. Em produção, use um usuário
MySQL com `SELECT` restrito às tabelas necessárias; a aplicação não executa
escritas. A conexão TLS real e os privilégios precisam ser conferidos no
servidor remoto antes de anunciar a disponibilidade. Nunca inclua o CA, a
chave ou a senha no Git.

`matching_development` foi criado para esta aplicação e é separado do banco institucional original. Em 15/10/2026, recebeu os 1.000 itens encontrados aprovados, com IDs 1001–2000 e estado `ACTIVE`. As consultas rotuladas permanecem nos JSONL de `evaluation/final/`; a divisão 700/300 existe apenas no manifesto e no avaliador. A carga e sua conferência estão descritas em `evaluation/final/README.md`.

## Execução

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

A documentação interativa fica disponível em `http://127.0.0.1:8000/docs`
no ambiente local e em
`https://busca-inteligente-achados-perdidos.onrender.com/docs` no Render.
No Swagger, clique em **Authorize** e informe a mesma chave configurada em
`SERVICE_API_KEY` no Render; depois, abra `POST /matches/search`, clique em
**Try it out**, preencha `description` e `top_k` e execute. A chave é enviada
no cabeçalho `X-Service-Key`; a página de documentação é pública, mas a busca
continua exigindo a chave. Não coloque a chave no corpo da requisição, em
capturas de tela ou no repositório.
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

Uma resposta tem esta estrutura (valores ilustrativos):

```json
{
  "returned_count": 1,
  "processing_time_ms": 12.3,
  "matches": [
    {
      "item_id": 1001,
      "name": "Celular preto",
      "description": "Celular em tom preto, com pequena marca azul.",
      "location": "Biblioteca",
      "category": "Eletrônicos",
      "found_on": "2026-08-01T08:00:00",
      "cosine_score": 0.875303,
      "levenshtein_score": 0.738462,
      "final_score": 0.806882
    }
  ]
}
```

`processing_time_ms` é medido em cada requisição; os escores e a ordem mudam
com o catálogo consultado. A resposta acima não representa uma medição remota.

### Transporte e limite na hospedagem prevista

O [Render fornece TLS e redireciona HTTP para HTTPS](https://render.com/docs/web-services)
na borda do Web Service; a aplicação recebe tráfego HTTP após a terminação TLS.
O [plano Free permite uma instância e hiberna após 15 minutos sem tráfego](https://render.com/docs/free),
com retorno que pode levar cerca de um minuto. Por isso o limite fica no
processo único, sem gateway próprio. O HTTPS do domínio implantado e o limite
observado externamente ainda exigem teste após publicação. O tráfego API–Aiven deve ser
validado separadamente com o CA da Aiven.

## Implantação de demonstração no Render e na Aiven

Condições consultadas em 23/10/2026: o [Render Free](https://render.com/docs/free)
oferece uma instância com [0,1 CPU e 512 MB de RAM](https://render.com/docs/compute-plans),
750 horas de instância por mês e hiberna após 15 minutos sem tráfego. A retomada
pode levar cerca de um minuto. A instância não tem disco persistente nem escala
horizontal. No workspace Hobby, há [5 GB de tráfego de saída](https://render.com/docs/outbound-bandwidth)
e [500 minutos de build](https://render.com/docs/build-pipeline) por mês;
o excedente de tráfego público custa US$ 0,15/GB. Com pagamento cadastrado,
excedentes podem ser cobrados, e sem pagamento
o serviço ou novos builds podem ser suspensos. Tráfego iniciado pelo serviço
para um banco externo também pode motivar suspensão no plano Free. O Render
desaconselha esse plano para aplicações de produção; use-o aqui somente para a
demonstração acadêmica, sem promessa de disponibilidade contínua.

A [Aiven MySQL Free](https://aiven.io/docs/products/mysql/concepts/mysql-free-tier)
e sua [tabela de preços](https://aiven.io/pricing/mysql) indicam US$ 0/mês,
sem cartão exigido para cadastro, 1 CPU, 1 GB de RAM, 1 GB de armazenamento,
um nó e até 76 conexões. Há uma instância gratuita de MySQL por organização,
sem região fixa selecionável, suporte ou SLA de 99,99%. O serviço pode ser
desligado por falta de uso; há aviso antes do desligamento por inatividade
contínua. Confira a seleção Free e o custo mostrado na conta antes de criar o
recurso. Não converta o serviço para um plano pago automaticamente.

A criação no [console Aiven](https://aiven.io/docs/products/mysql/get-started)
segue **Services > Create service > MySQL > Free > Create service**. Aguarde o
estado `Running`; a região gratuita é escolhida pela Aiven. Em **Connect >
Databases > Create database**, crie `matching_development`, conforme a
[instrução oficial](https://aiven.io/docs/products/mysql/howto/create-database).
Com uma conexão administrativa protegida por TLS e o [CA do projeto
Aiven](https://aiven.io/docs/platform/concepts/tls-ssl-certificates), crie
o acesso ao schema e confirme que `SHOW TABLES FROM matching_development`
não retorna linhas. Execute `evaluation/final/load.sql` uma única vez nesse
schema remoto vazio e, depois, `evaluation/final/verify_load.sql`. Compare os
1.000 IDs distintos e `ACTIVE`, 700/300 IDs dos splits e dez categorias com
100 itens cada com `evaluation/final/README.md`. O schema local
já está preenchido e não deve receber nova carga. As consultas rotuladas ficam
nos JSONL, fora do MySQL. Crie uma conta de serviço separada e conceda apenas
`SELECT` sobre `matching_development.item` e `matching_development.category`;
confira `SHOW GRANTS` dessa conta e teste que ela não pode escrever. A
[Aiven informa que usuários adicionais recebem privilégios administrativos
por padrão](https://aiven.io/docs/products/mysql/howto/manage-service-users);
portanto não use uma conta criada sem restrição na API. Crie uma conta com
permissões granulares e confira os privilégios efetivos antes de configurá-la
no Render. Não use `avnadmin` na API.

No [painel do Render](https://render.com/docs/web-services), escolha **New >
Web Service**, conecte o repositório e selecione a revisão Git aprovada. Use
o plano Free, runtime
Python 3, build `pip install .`, start
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`, uma instância e health check
`/health`. Desative a publicação automática até a revisão da configuração.
Em **Settings > Auto-Deploy**, selecione **Off**; futuras implantações podem
usar **Deploys > Manual Deploy > Deploy a specific commit**, conforme a
[documentação do Render](https://render.com/docs/deploys). A criação do serviço
dispara a primeira implantação, portanto configure segredos e banco antes de
considerá-lo pronto para uso.
Informe `DB_HOST`, `DB_PORT`, `DB_NAME=matching_development`, `DB_USER`,
`DB_PASSWORD`, `SERVICE_API_KEY`, `DB_REQUIRE_TLS=true`,
`DB_SSL_CA=/etc/secrets/aiven-ca.pem`, `RATE_LIMIT_PER_MINUTE=60`,
`MATCH_METHOD=hybrid`, `MATCH_ALPHA=0.5` e `MATCH_BETA=0.5` nas variáveis de
ambiente. Salve `aiven-ca.pem` como [Secret File do Render](https://render.com/docs/configure-environment-variables#secret-files),
fora do repositório. O [Render instala Python a partir de `.python-version`](https://render.com/docs/python-version).
O TLS público termina na borda do Render, que fornece certificado gerenciado e
redireciona HTTP para HTTPS. O TLS da conexão com a Aiven é verificado
separadamente pelo cliente MySQL. Se o CA girar, atualize o Secret File e
reteste a busca.

Antes de publicar, repita localmente `pip install .` e o mesmo comando de início,
com `PORT` definido; no PowerShell, use `$env:PORT=8000` e
`python -m uvicorn app.main:app --host 0.0.0.0 --port $env:PORT`. A checagem
local de CA válido/inválido cobre a leitura do certificado; uma busca real na
URL publicada deve comprovar a negociação TLS com a Aiven. Registre a revisão,
a URL e a região efetiva sem copiar segredos para a documentação.

Após a publicação, faça `/health` por HTTPS e buscas autorizadas positiva e
sem correspondência. Confira 401 para `X-Service-Key` ausente e inválida, 429
com `Retry-After` após 60 buscas autorizadas na janela de 60 segundos, e 503
seguro quando o banco falhar. `/health` mede somente o processo e pode continuar
em 200 durante falha do MySQL. Uma consulta sem correspondência ainda retorna
sugestões ranqueadas. Meça separadamente a primeira resposta, a resposta quente
e a retomada após hibernação com os 1.000 itens consultados via MySQL; registre
`processing_time_ms` e o tempo HTTP de ponta a ponta. A latência de E07 foi
obtida com `TestClient` local e catálogo em memória, portanto não representa
essa busca remota.

Na implantação de 23/10/2026, o painel **Deploys** do Render confirma o
primeiro deploy `Live` da revisão `332faf9` (commit completo
`332faf96266807fef9bef380e17340cd96d2c087`), na região Ohio (US East).
A API respondeu por HTTPS em
`https://busca-inteligente-achados-perdidos.onrender.com`. A autora mediu uma
busca positiva sobre o MySQL publicado: HTTP 200, item 1001 em primeiro lugar,
`processing_time_ms=1774,57` e 2.091,3 ms de ponta a ponta no PowerShell. Uma
consulta rotulada sem correspondência retornou cinco sugestões, como prevê o
contrato atual: `processing_time_ms=566,282` e 14.185,4 ms de ponta a ponta.
Esses valores são uma amostra por consulta, não percentis nem tempos do
experimento local. A diferença entre o tempo da segunda resposta no cliente e
na API ainda não foi atribuída a hibernação ou a outra causa.

Depois de mais de 20 minutos sem acesso público, uma busca positiva idêntica
levou 54.357,7 ms no PowerShell, dos quais 1.658,349 ms foram medidos pela
API no processamento da busca. Uma repetição imediata levou 547,1 ms no
PowerShell e 355,001 ms na API. Ambas retornaram HTTP 200, cinco sugestões e
o item 1001 em primeiro lugar. A primeira demora é compatível com a retomada
do Render Free após ociosidade. Os logs da autora mostram o encerramento da
instância às 23:09, nova inicialização às 23:47 e as duas buscas logo após a
retomada; os health checks internos pararam nesse intervalo. Assim, a primeira
amostra inclui o despertar da instância, enquanto `processing_time_ms` começa
somente quando a busca chega à API. São duas amostras e não representam
percentis de latência.

Na mesma implantação, a configuração não sensível conferida no painel Render
foi `DB_NAME=matching_development`, `DB_USER=matching_reader`,
`DB_REQUIRE_TLS=true`, `DB_SSL_CA=/etc/secrets/aiven-ca.pem` e
`RATE_LIMIT_PER_MINUTE=60`, com o Secret File `aiven-ca.pem`. A autora também
confirmou `MATCH_METHOD=hybrid`, `MATCH_ALPHA=0.5` e `MATCH_BETA=0.5`. O
contexto TLS criado em `app/config.py` verifica o CA e a identidade do host;
as buscas públicas bem-sucedidas confirmam que essa configuração conseguiu
consultar a Aiven. O teste de CA inválido foi local, sem substituir o certificado do
serviço publicado.

Para monitorar, confira o painel do Render (deploys, logs e franquias) e o
painel da Aiven (estado, conexões, armazenamento e aviso de inatividade).
Mantenha os logs sem corpo da consulta, credencial ou senha. Em falha de
implantação, use o rollback do Render para uma das duas revisões anteriores
disponíveis no plano Free, quando já houver um deploy anterior bem-sucedido.
No primeiro deploy, ainda não existia alvo de rollback. Confira as
variáveis e o Secret File e repita
`/health` e a busca real. Preserve o schema sintético; se ele precisar ser
recriado, use um schema remoto novo e vazio e reconfira `verify_load.sql`
antes de redirecionar a API. Não restaure dados do schema local por sobrescrita.

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
do banco, `/health` e inspeção dos logs. Após configurar Render e Aiven,
repita por HTTPS contra a URL publicada e confira também certificado TLS,
permissões `SELECT` e comportamento após hibernação. A latência HTTP medida
localmente com catálogo em memória na avaliação não representa o tempo de busca
dos 1.000 itens via MySQL remoto.
