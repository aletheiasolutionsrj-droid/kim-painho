# 🔮 Kim Painho — um oráculo de perguntas e respostas sobre o seu próprio acervo e sobre acervos diversos baixados em coleções pré-cadastradas.

O **Kim Painho** é um sistema de **busca e perguntas com IA** que roda no seu computador. Você monta um acervo com **vídeos do YouTube, PDFs e podcasts/áudios**, faz perguntas em português e recebe uma resposta escrita pela IA, **com as fontes**: o vídeo no minuto exato, a página do PDF ou o minuto do áudio onde o assunto foi tratado.

Em termos técnicos, é um sistema **RAG** (*Retrieval-Augmented Generation*): os textos são cortados em trechos, transformados em vetores e guardados num banco vetorial. Na hora da pergunta, o sistema busca os trechos mais parecidos, reordena os melhores e entrega só eles para a IA responder.

## 🎯 Por que este projeto existe

O Kim Painho nasceu com dois objetivos:

- **Ajudar criadores de conteúdo a recuperar o histórico do próprio trabalho.** Quem produz vídeos, podcasts e textos por anos acumula centenas de horas de material e perde a memória do que já disse. Com o acervo indexado, o criador encontra em segundos em qual vídeo, em que minuto ou em que página tratou de um assunto, e pode revisitar, citar e reaproveitar o que já produziu.
- **Ajudar pessoas a estudar mais a fundo os assuntos que os criadores abordam**, sobre os temas mais variados: história, geografia, filosofia, ciência, política, cultura e o que mais houver. Em vez de assistir a horas de vídeo atrás de uma resposta, o estudante pergunta e recebe os trechos relevantes **com a fonte**, para ir direto ao original e conferir.

Acreditamos que a **informação descentralizada e distribuída** ajuda no crescimento de uma sociedade mais consciente e saudável. Quando cada pessoa pode organizar, consultar e aprofundar o conhecimento que lhe interessa, no seu próprio computador e sem depender de uma única plataforma, o acesso à informação fica mais livre, e o estudo mais crítico e autônomo. Por isso a ferramenta roda localmente, cada pessoa monta o seu acervo e **toda resposta aponta para a fonte original**: a IA ajuda a encontrar e a entender, mas quem confere e decide é você.

> ⚠️ **Sobre o conteúdo.** Este projeto é só a ferramenta: **ele não inclui nem distribui nenhum vídeo, legenda, PDF ou áudio.** Cada pessoa monta o seu acervo com material que tem o direito de usar. Respeite os direitos autorais e os termos de uso do YouTube. Conteúdo pago (como assinaturas em PDF) é só para uso pessoal e **não deve ser publicado**.

## 🔓 Uso livre e adaptação
 
O Kim Painho é **software livre, sob a licença MIT**: você pode usar, copiar, modificar, distribuir e até usar comercialmente, sem pedir permissão e sem pagar nada. A única exigência é manter o aviso de licença e de autoria nas cópias. Contribuições, sugestões e adaptações são bem-vindas.
 
### 🏢 Também serve para uso interno em empresas
 
O que o sistema faz com vídeos e podcasts, ele faz com qualquer conjunto de documentos: indexa o conteúdo, encontra os trechos certos e responde **apontando a fonte exata**, com a página do PDF ou o minuto do áudio. Isso é útil em qualquer lugar onde achar a informação certa, rápido e com comprovação, faz diferença. Alguns exemplos:
 
- **Procedimentos operacionais padrão (POPs):** "Qual é o procedimento para recolher um lote com desvio de qualidade?" A resposta vem com o POP e a página.
- **Manuais técnicos e de equipamentos:** o técnico pergunta como calibrar uma máquina e recebe o trecho do manual, em vez de folhear um PDF de 300 páginas.
- **Normas, políticas e compliance:** segurança do trabalho, políticas de RH, código de conduta, requisitos regulatórios e auditorias.
- **Onboarding:** novos colaboradores tiram dúvidas sobre processos, benefícios e ferramentas sem depender de quem já sabe.
- **Treinamentos e reuniões gravadas:** o áudio ou o vídeo é transcrito pelo Whisper e fica consultável pelo minuto em que o assunto foi tratado.
- **Base de conhecimento do suporte:** o atendente consulta o histórico de soluções e a documentação do produto.
- **Escritórios e consultorias:** contratos, pareceres, atas e normas internas de um cliente ou de um projeto.
 
Cada área pode ter o **seu próprio acervo** (Qualidade, RH, Manutenção, Jurídico…), e o botão de consulta já permite buscar só em PDFs ou só em áudios.
 
### ⚠️ O que ajustar antes de usar com documentos sigilosos
 
O projeto é um ponto de partida, e algumas coisas precisam de atenção em ambiente corporativo:
 
- **Privacidade da IA.** Hoje a resposta é escrita pela Groq, na nuvem: a pergunta e os trechos selecionados saem do seu computador. Para documentos confidenciais, troque por um modelo que rode localmente (o Ollama, que o projeto já usa para os embeddings, também executa modelos de linguagem) ou por um serviço aprovado pela sua empresa. Isso exige alterar `geracao.py` e `config.py`.
- **Acesso e permissões.** O sistema não tem login de usuários nem permissões por acervo. Há só uma senha opcional para a Administração. Em uma empresa, coloque-o atrás da rede interna ou de um proxy com autenticação, e não o exponha à internet.
- **Verifique as respostas.** A IA pode errar. Em procedimentos críticos (saúde, segurança, normas), sempre confira no documento original pelo link da fonte.

---

## 📑 Sumário

1. [O que o sistema faz](#-o-que-o-sistema-faz)
2. [Como funciona por dentro](#-como-funciona-por-dentro)
3. [Instalação passo a passo (para iniciantes)](#-instalação-passo-a-passo-para-iniciantes)
4. [Como cadastrar a chave da Groq](#-como-cadastrar-a-chave-da-groq)
5. [Primeiros passos](#-primeiros-passos)
6. [Configurações opcionais](#-configurações-opcionais)
7. [Uso no dia a dia](#-uso-no-dia-a-dia)
8. [Problemas comuns](#-problemas-comuns)
9. [Para desenvolvedores](#-para-desenvolvedores)

---

## ✨ O que o sistema faz

### 🔮 Página principal: o Oráculo

- **Perguntas em linguagem natural**, com resposta escrita pela IA e baseada somente no que foi encontrado no acervo.
- **Fontes numeradas.** A IA cita "Fonte 1", "Fonte 2"… e o painel ao lado mostra cada uma com o mesmo número:
  - **Vídeos:** botão que abre o YouTube **no ponto exato** em que o assunto foi falado.
  - **PDFs:** página exata (com a numeração do autor, quando houver) e link que abre o PDF nela.
  - **Podcasts e áudios:** minuto do áudio em que o trecho foi falado.
- **Passe o mouse no 👁️** de uma fonte para ler o título completo e o texto do trecho.
- **De onde consultar:** todo o acervo, apenas vídeos, apenas PDFs ou apenas áudio/podcast.
- **Modos de busca:** por *contexto* (significado), por *expressão exata* (a frase literal) ou *ambos*.
- **Grau de vidência:** controla o quanto a IA pode ser criativa. Baixo fica mais fiel ao acervo.
- **Ignorar o início dos vídeos:** descarta os primeiros minutos (vinhetas e apresentações) na consulta.
- **Resultados da busca** e **contexto para a IA:** você escolhe quantos trechos buscar e quantos enviar para a IA.
- **Vários acervos:** troque de acervo na barra lateral (por exemplo, um por autor ou tema).

### 🛠️ Página de Administração

Abra pelo botão **Administração do acervo**, na barra lateral. Tudo roda em **tarefas em segundo plano**, com barra de progresso, registro detalhado e botão de cancelar: você pode continuar usando o sistema enquanto elas trabalham.

| Seção | O que faz |
|---|---|
| **📚 Acervos** | Lista, cria, edita e exclui acervos. Cada acervo escolhe o seu modelo de embedding. O **glossário de nomes** ensina ao sistema a grafia correta de nomes próprios (ajuda o Whisper a transcrever bem). |
| **➕ Vídeos do YouTube** | Cole links de vídeos, playlists ou **canais inteiros** para baixar as legendas. Também importa legendas que você já tem em arquivo (`.json`, `.srt`, `.vtt`), em lote ou de uma pasta. Pode **traduzir** para o português legendas de vídeos em outros idiomas (e, se quiser, o título também). Respeita o limite do YouTube, que pode bloquear o IP por algumas horas: nesse caso a tarefa para e pode ser retomada. |
| **➕ PDFs** | Envia PDFs e indexa página por página, preservando a página para o link da fonte. |
| **➕ Podcast e áudio** | Transcreve áudios (mp3, wav etc.) com o **Whisper** local, ou importa uma transcrição pronta com tempos. |
| **➕ Vídeos sem legenda** | Lista os vídeos que o YouTube não tinha legenda e permite transcrevê-los com o Whisper. |
| **🔄 Atualização automática** | Cadastre um canal para um acervo e, **uma vez por dia, ao abrir o site**, o sistema cria uma tarefa que inclui os vídeos novos. Pode ativar, desativar, atualizar na hora ou excluir. |
| **🗂️ Documentos** | Tabela de tudo que está no acervo, com filtros, datas de publicação, do arquivo e do processamento. Permite editar título e data e **excluir documentos** com todos os seus trechos. |
| **⚙️ Tarefas** | Acompanhe, cancele, repita ou retome as tarefas (e leia o registro detalhado de cada uma). |
| **💾 Backup / ↩️ Restore** | Cria e restaura cópias (snapshots) de um acervo. |
| **❤️ Saúde e índices** | Diagnostica o banco e os serviços (Qdrant, Ollama, chave da Groq) e cria índices que estiverem faltando. |

---

## 🧠 Como funciona por dentro

```
   Você  ──pergunta──►  Streamlit (app web)
                           │
         ┌─────────────────┼──────────────────────────┐
         ▼                 ▼                          ▼
      Ollama            Qdrant                      Groq
   (gera os vetores)  (banco vetorial)   (IA que escreve a resposta)
     roda local        roda local            na nuvem, com a sua chave
```

| Peça | Papel | Onde roda |
|---|---|---|
| **Streamlit** | A interface web (Oráculo e Administração) | No seu computador |
| **Qdrant** | Banco de dados vetorial: guarda os trechos e faz a busca por significado | No seu computador |
| **Ollama** | Gera os *embeddings* (modelos `nomic-embed-text` ou `bge-m3`) | No seu computador |
| **fastembed** | Reordena (*rerank*) os melhores trechos | No seu computador |
| **Whisper** (faster-whisper) | Transcreve áudio | No seu computador |
| **Groq** | A IA (LLM) que escreve a resposta | Na nuvem (precisa de internet e de uma chave gratuita) |

O modelo nomi-embed-text é especializado no idioma inglês e o bge-m3 em multi-idiomas. Para conteúdo em português, recomendo o uso do bge-m3.

**Privacidade:** o seu acervo e o banco de dados ficam no seu computador. Para escrever cada resposta, apenas a **pergunta e os trechos selecionados** são enviados à Groq.

Tudo roda em **Docker**, um programa que empacota e executa essas peças sem você instalar nada na mão (nem Python).

---

## 🚀 Instalação passo a passo (para iniciantes)

Você vai precisar de: um computador com **8 GB de RAM** (recomendado 16 GB para transcrever áudio), cerca de **15 GB livres em disco**, **internet** e cerca de **30 minutos** na primeira vez (os modelos de IA são baixados uma vez só).

### Passo 1 — Instalar o Docker

**Windows 10/11**
1. Baixe o **Docker Desktop** em <https://www.docker.com/products/docker-desktop/> e execute o instalador.
2. Mantenha marcada a opção **"Use WSL 2"** (é o padrão).
3. Reinicie o computador quando pedir e abra o **Docker Desktop**. Aceite os termos e espere o ícone da baleia ficar **verde / "Engine running"**.
4. Se aparecer um erro sobre *virtualização*, ela precisa ser ativada na BIOS do computador (opção "Intel VT-x" ou "AMD-V"). Pesquise o modelo da sua placa-mãe + "ativar virtualização".

**macOS**
1. Baixe o Docker Desktop para o seu chip (**Apple Silicon** ou **Intel**) no mesmo endereço e arraste para *Aplicativos*.
2. Abra o Docker Desktop e espere iniciar.

**Linux (Ubuntu/Debian e similares)**
1. Siga o guia oficial: <https://docs.docker.com/engine/install/>
2. Depois, para usar sem `sudo`: `sudo usermod -aG docker $USER` e saia da sessão e entre de novo.

Para conferir, abra um terminal (no Windows: **PowerShell**; procure no menu Iniciar) e digite:

```bash
docker --version
docker compose version
```

Se aparecerem números de versão, está tudo certo. Se aparecer "não reconhecido", reinicie o computador e confira se o Docker Desktop está aberto.

⚠️ **ATENÇÃO!**
DEIXE SEMPRE O DOCKER DESKTOP LIGADO PARA RODAR A APLICAÇÃO.

### Passo 2 — Baixar o projeto

Você **não precisa** saber usar o GitHub. Escolha uma das opções:

**Opção A — Baixar o ZIP (mais simples)**
1. Na página do projeto no GitHub, clique no botão verde **`< > Code`** e depois em **`Download ZIP`**.
2. Extraia o ZIP em uma pasta simples, por exemplo `C:\kim-painho` (evite caminhos com acentos e pastas sincronizadas, como OneDrive).

**Opção B — Usando o Git** (permite atualizar com um comando)
1. Instale o Git: <https://git-scm.com/downloads>
2. No terminal:
   ```bash
   git clone https://github.com/aletheiasolutionsrj-droid/kim-painho.git kim-painho
   ```
   *(troque pelo endereço real do projeto, o mesmo que aparece no botão `Code`)*

### Passo 3 — Cadastrar a chave da Groq

Siga a seção [Como cadastrar a chave da Groq](#-como-cadastrar-a-chave-da-groq), logo abaixo. **Sem a chave, o sistema não consegue escrever as respostas.**

### Passo 4 — Ligar o sistema

No terminal, entre na pasta do projeto e rode:

```bash
cd C:\kim-painho
docker compose up -d --build
```

- Na **primeira vez** isso leva vários minutos: o Docker baixa as imagens e constrói o aplicativo.
- O Ollama também baixa os modelos de embedding **em segundo plano**. Para acompanhar:
  ```bash
  docker logs -f ollama_container
  ```
  Quando aparecer **`OLLAMA PRONTO`**, está pronto (saia do acompanhamento com `Ctrl + C`).

### Passo 5 — Abrir o sistema

Abra no navegador: **<http://localhost:8501>**

Pronto! Na próxima vez, basta abrir o Docker Desktop (os serviços reiniciam sozinhos) e acessar o mesmo endereço.

---

## 🔑 Como cadastrar a chave da Groq

A **Groq** é o serviço que roda a IA que escreve as respostas. O uso básico é **gratuito** (com limite de requisições por minuto/dia), e você só precisa de uma conta.

### 1. Criar a chave

1. Acesse <https://console.groq.com/keys> e crie uma conta (pode entrar com Google ou GitHub).
2. Clique em **Create API Key**, dê um nome (por exemplo, `kim-painho`) e confirme.
3. **Copie a chave agora**: ela começa com `gsk_` e só é mostrada uma vez. Se perder, crie outra.

### 2. Guardar a chave no arquivo `.env`

O `.env` é um arquivo de texto, na **mesma pasta do `docker-compose.yaml`**, onde ficam as senhas e as chaves. Ele fica só no seu computador e **nunca vai para o GitHub**.

1. Na pasta do projeto, faça uma cópia de **`.env.example`** com o nome **`.env`**:
   - **Windows (PowerShell):** `Copy-Item .env.example .env`
   - **macOS / Linux:** `cp .env.example .env`
2. Abra o `.env` no Bloco de Notas (Windows: `notepad .env`) e troque a linha da chave, **sem aspas e sem espaços**:
   ```
   GROQ_API_KEY=gsk_abc123...sua_chave_inteira
   ```
3. Salve o arquivo.
4. Se o sistema já estava ligado, aplique a mudança: `docker compose up -d`

> **Dica para Windows:** o arquivo precisa se chamar exatamente **`.env`**, não `.env.txt`. No Explorador de Arquivos, ative *Exibir → Mostrar → Extensões de nomes de arquivos* para conferir.

### 3. Conferir

Abra **Administração → ❤️ Saúde e índices**. A linha da Groq deve aparecer como **"configurada"**.

> 🔒 **Cuidado:** nunca cole a sua chave em fóruns, prints ou no GitHub. Se ela vazar, apague-a em <https://console.groq.com/keys> e crie outra.

---

## 🧭 Primeiros passos

1. Abra <http://localhost:8501>. Existe um acervo inicial vazio, chamado **Meu acervo**.
2. Clique em **Administração do acervo** (barra lateral).
3. Em **📚 Acervos → Novo acervo**, crie um acervo com o nome que quiser (opcional: você pode usar o inicial).
4. Em **➕ Adicionar conteúdo**, inclua algum material:
   - **Vídeos do YouTube:** cole o link de um vídeo ou de um canal (comece com poucos vídeos para testar) e clique em **Adicionar à fila**.
   - **PDFs:** envie os arquivos.
   - **Podcast e áudio:** envie o áudio (o Whisper transcreve) ou uma transcrição pronta.
5. Acompanhe em **⚙️ Tarefas**. Quando terminar, confira em **🗂️ Documentos**.
6. Clique em **Voltar ao Oráculo**, escolha o acervo, escreva a pergunta e clique em **🔮 Consultar**.

---

## ⚙️ Configurações opcionais

Ficam no arquivo `.env` (veja o `.env.example`). Depois de mudar, rode `docker compose up -d`.

| Variável | Para que serve | Padrão |
|---|---|---|
| `GROQ_API_KEY` | Chave da Groq (**obrigatória**) | — |
| `ADMIN_PASSWORD` | Se preenchida, a página de Administração pede essa senha | vazio (sem senha) |
| `MODELOS_OLLAMA` | Modelos de embedding que o Ollama baixa, separados por espaço | `nomic-embed-text bge-m3` |
| `WHISPER_DEVICE` | `auto`, `cpu` ou `cuda` (placa NVIDIA) | `auto` |
| `WHISPER_COMPUTE_TYPE` | Precisão do Whisper (`int8`, `float16`...) | automático |

**Qual modelo de embedding escolher?** Cada acervo escolhe o seu ao ser criado. O `nomic-embed-text` é leve e foi o padrão do projeto. O `bge-m3` é multilíngue e costuma ser uma boa opção para português e para misturar idiomas. Os vetores dos dois têm tamanhos diferentes: **para trocar o modelo de um acervo é preciso reindexar o conteúdo**.

**Outros ajustes** (no código): o modelo de IA da Groq fica em `config.py` (`MODELO_LLM`).

### 🔐 Segurança

- O sistema foi pensado para uso **pessoal e local**. A página principal **não tem login**.
- Por padrão, a porta 8501 fica visível para outros aparelhos da sua rede. Para deixar **só o seu computador** acessar, no `docker-compose.yaml` troque `"8501:8501"` por `"127.0.0.1:8501:8501"` (e faça o mesmo com as portas do Qdrant e do Ollama).
- Não publique o sistema na internet sem colocar autenticação na frente.

---

## 📅 Uso no dia a dia

| O que fazer | Comando (na pasta do projeto) |
|---|---|
| Ligar | `docker compose up -d` |
| Desligar (mantém os dados) | `docker compose stop` |
| Ver o que está acontecendo | `docker compose logs -f web_app` |
| Atualizar para uma nova versão | `git pull` (ou baixe o ZIP novo e copie por cima) e depois `docker compose up -d --build` |
| Reiniciar só o aplicativo | `docker restart omniarquivo_app` |

**Onde ficam os seus dados**
- **Banco vetorial (os acervos indexados):** volume do Docker `iakimpaim_qdrant_data`.
- **Modelos do Ollama:** volume `iakimpaim_ollama_data`.
- **Backups:** pasta `backups/acervos` do projeto (use a página **Backup**).
- **Configuração dos acervos e tarefas:** pasta `data/` do projeto.

> ⚠️ O comando `docker compose down -v` **apaga os volumes**, ou seja, **todos os acervos indexados**. Faça um backup antes.

---

## 🩺 Problemas comuns

| Sintoma | O que fazer |
|---|---|
| `Cannot connect to the Docker daemon` / erro ao rodar `docker` | O Docker Desktop não está aberto. Abra e espere ficar verde. |
| A página não abre em `localhost:8501` | Veja `docker compose ps`. Se o `omniarquivo_app` caiu, leia `docker compose logs web_app`. Se a porta 8501 estiver ocupada, troque o primeiro número em `ports` (por exemplo `"8502:8501"`). |
| "GROQ_API_KEY ausente" ou erro 401 | A chave não foi lida. Confira o nome `.env` (sem `.txt`), a linha `GROQ_API_KEY=gsk_...` sem aspas, e rode `docker compose up -d`. |
| Erro de embedding / "model not found" ao adicionar conteúdo | O Ollama ainda está baixando os modelos. Acompanhe com `docker logs -f ollama_container` e aguarde o `OLLAMA PRONTO`. |
| A primeira pergunta demora | O modelo de reordenação (*reranker*) é baixado na primeira consulta. Depois fica rápido. |
| "Limite de requisições" da Groq | Aguarde alguns minutos: o plano gratuito tem limites. |
| O YouTube bloqueou o download de legendas | É temporário (cerca de 6 horas). A tarefa para sozinha; depois clique em **▶️ Retomar** na aba Tarefas. Use o limite de vídeos por tarefa em canais grandes. |
| A transcrição de áudio grande falha ou a tarefa fica "Interrompida" | Quase sempre é falta de memória. Aumente a memória do Docker (6 GB ou mais) e use o modelo **small** ou **medium**. No Windows com WSL 2, crie o arquivo `C:\Users\SEU-USUARIO\.wslconfig` com `[wsl2]` e `memory=8GB`, depois rode `wsl --shutdown` e reabra o Docker Desktop. No macOS, use *Settings → Resources*. |
| O Windows mostra erros estranhos no `entrypoint.sh` | O arquivo precisa ter fim de linha do tipo LF. O projeto já inclui um `.gitattributes` para isso. |

---

## 👩‍💻 Para desenvolvedores

**Estrutura do projeto**

```
├── app.py                  Página principal (Oráculo)
├── ui.py                   Componentes visuais do Oráculo
├── busca.py                Busca no Qdrant (filtros, modos de busca)
├── reranking.py            Reordenação dos resultados
├── geracao.py              Monta o contexto e chama a IA (Groq)
├── config.py / clientes.py Configuração e clientes (Qdrant, Groq)
├── pages/                  Página de Administração (Streamlit)
├── admin/                  Painel: tarefas, worker, catálogo de acervos, atualização automática
│   └── telas/              Telas de cada seção do menu
├── ingestao/               Pipeline: YouTube, PDF, áudio/Whisper, chunking, embeddings, Qdrant
├── backup_qdrant.py        Backup de acervos (usado pela página Backup)
├── tests/                  Testes automatizados (sem precisar de Qdrant, Ollama ou navegador)
├── data/                   Estado de cada instalação (ignorado pelo Git, exceto data/entrada/.gitkeep)
├── Dockerfile · docker-compose.yaml · entrypoint.sh
└── requirements.txt
```

**Executar os testes** (com o sistema ligado):

```bash
docker exec omniarquivo_app python tests/test_ingestao.py
docker exec omniarquivo_app python tests/test_admin.py
docker exec omniarquivo_app python tests/test_telas.py
docker exec omniarquivo_app python tests/test_busca.py
```

**Ingestão pela linha de comando** (alternativa à página de Administração):

```bash
docker exec omniarquivo_app python -m ingestao.cli --help
```

---

## 📄 Licença

A definir pelo autor do projeto.

## 🙏 Tecnologias

[Streamlit](https://streamlit.io) · [Qdrant](https://qdrant.tech) · [Ollama](https://ollama.com) · [Groq](https://groq.com) · [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) · [fastembed](https://github.com/qdrant/fastembed)
