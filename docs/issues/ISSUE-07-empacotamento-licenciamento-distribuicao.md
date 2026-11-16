# ISSUE-07: Sistema de Empacotamento, Licenciamento Criptográfico e Distribuição Comercial

**Status:** Aberta  
**Prioridade:** Alta  
**Módulos Afetados:** Infraestrutura de build, `main.py`, novo módulo de licenciamento (`licensing/`).

---

## 1. Contexto Comercial

Hoje, o sistema exige um ambiente de desenvolvimento configurado (`Python 3.10+`, criação de `.venv`, `pip install -r requirements.txt` e scripts `.bat`).

Para que o software possa ser comercializado e instalado em clientes reais por um vendedor ou suporte técnico:
1. O cliente final não pode ter acesso ao código-fonte aberto em Python (risco de pirataria e perda de propriedade intelectual).
2. A instalação deve ser realizada em **1 clique** através de um instalador executável padrão do Windows.
3. Deve existir um **mecanismo rigoroso de proteção e licenciamento**, impedindo cópias não autorizadas entre computadores.

---

## 2. Requisitos da Solução

### 2.1. Compilação e Proteção de Código (Nuitka / PyInstaller com Ofuscação)
* **Compilação Nativa:** Compilar os módulos Python em código de máquina C++ utilizando o **Nuitka** (que traduz o código Python para C antes da compilação com MSVC) ou empacotador nativo.
  - Vantagem: Elimina a descompilação trivial por bytecode (`.pyc`).
  - Performance: Aumenta a velocidade de execução das rotinas numéricas e de processamento de imagem.
* **Instalador Único (`Setup.exe`):**
  - Gerado com **Inno Setup** (permissivo, padrão da indústria).
  - Instalação silenciosa em `C:\Program Files\<Nome do Software>\`.
  - Criação de atalhos na Área de Trabalho e inicialização automática como serviço/bandeja no boot do Windows.

### 2.2. Sistema de Licenciamento Criptográfico (Modelo Monocypher do CNC CAM)
No `CNC CAM C++`, a equipe implementou a ferramenta `license_tool` com a biblioteca de criptografia **Monocypher** (Ed25519 e Chacha20). O mesmo padrão deve ser adotado aqui:
* **Assinatura Digital Assimétrica (Curva Elíptica Ed25519):**
  - As chaves de licença são geradas exclusivamente pelo desenvolvedor usando uma **chave privada mestra**.
  - O aplicativo cliente embutido contém apenas a **chave pública** para validar matematicamente se a licença é legítima, impossibilitando a criação de "geradores de seriais piratas" (Keygens).
* **Identificação Única da Máquina (*Hardware Fingerprint*):**
  - A licença é amarrada aos identificadores físicos do hardware: UUID da Placa-Mãe (`wmic csproduct get uuid`), Serial do Disco Principal e MAC Address da placa de rede.
  - Uma licença copiada para outro PC torna-se automaticamente inválida.
* **Modelos Comerciais Suportados pelo Arquivo de Licença (`.lic`):**
  - **Licença Mensal / SaaS:** Contém carimbo de validade UTC (`valido_ate = 2026-12-31`). O relógio é validado contra servidores de horário (NTP) para impedir que o usuário atrase o relógio do Windows.
  - **Licença Perpétua:** Validade vitalícia com bloqueio de atualizações após 12 meses.
  - **Módulos Ativos (*Feature Flags*):** Controle de quais módulos foram contratados pelo birô (ex: `modulo_nesting: true`, `modulo_tiling: true`, `modulo_cnc: false`).

### 2.3. Sistema de Atualização Automática (*Auto-Updater*)
* O aplicativo consulta periodicamente um endpoint de release (servidor próprio ou repositório protegido).
* Ao identificar uma versão nova, baixa o patch diferencial em segundo plano e solicita autorização do operador para reiniciar já atualizado.

---

## 3. Critérios de Aceite

1. O instalador `Setup.exe` deve instalar e rodar a aplicação em um Windows limpo (sem Python ou Git instalados) sem qualquer erro de dependência.
2. O sistema deve entrar em modo de demonstração (Trial de 14 dias ou com marca d'água na montagem) se não houver licença válida.
3. Ao inserir um arquivo `.lic` válido assinado pela chave privada mestra, todos os recursos liberados devem ser ativados instantaneamente.
