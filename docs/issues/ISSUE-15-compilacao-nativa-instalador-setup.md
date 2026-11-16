# ISSUE-15: Compilação Nativa e Instalador Executável (`Setup.exe`)

**Ordem de Execução:** 15º (Final)  
**Status:** Pronta para Início  
**Dependência:** Todas as issues anteriores concluídas  
**Módulos a Criar:** `scripts/compilar_nuitka.ps1`, `scripts/instalador.iss`.  
**Referência de Base:** Scripts de build e deploy de `c:\Users\flavi\Desktop\CNC CAM C++\CMakeLists.txt` e `windeployqt`.

---

## 1. Motivação Comercial

No ambiente corporativo de gráficas e birôs de impressão:
- Os operadores e donos de gráfica não possuem conhecimentos técnicos de terminal, Python, scripts `.bat` ou variáveis de ambiente `PATH`.
- Distribuir código Python em texto aberto expõe todo o segredo de negócio e propriedade intelectual do software.
- O produto final deve ser entregue como um instalador padrão Windows: **um único arquivo `Setup.exe` que instala em 1 clique**.

---

## 2. Requisitos Técnicos

### 2.1. Compilação com Nuitka (Código de Máquina C++)
Utilizar o **Nuitka** para traduzir todo o código Python em código de máquina nativo C++ e compilar via Microsoft Visual C++ (MSVC):
```powershell
nuitka --standalone --windows-disable-console `
       --enable-plugin=pyside6 `
       --output-dir=dist `
       --windows-icon-from-ico=assets/icone.ico `
       --remove-output `
       ui/app.py
```
* **Benefícios:**
  - Código-fonte 100% protegido contra descompilação (sem arquivos `.py` ou `.pyc` expostos).
  - Execução imediata sem necessidade de ter Python instalado no computador do cliente.
  - Otimizações de CPU em tempo de compilação (/O2 /Ob2).

### 2.2. Script de Empacotamento Inno Setup (`scripts/instalador.iss`)
* Geração do instalador padrão profissional para Windows 10 e Windows 11:
  - Assistente com Termos de Uso e EULA comercial.
  - Destino padrão: `C:\Program Files\AutoPrint Automation\`.
  - Criação de atalhos na Área de Trabalho e no Menu Iniciar.
  - Registro de inicialização automática em segundo plano para o vigia das impressoras na inicialização do Windows.
  - Assistente de desinstalação limpa (*Uninstall*) no Painel de Controle do Windows.
  - Instalação silenciosa do runtime Microsoft Visual C++ se necessário.

---

## 3. Critérios de Aceite

1. O instalador `Setup.exe` deve instalar o software com sucesso em um computador Windows limpo e recém-formatado.
2. O aplicativo deve abrir imediatamente com duplo clique no ícone da Área de Trabalho.
3. Nenhum arquivo de código Python legível deve estar presente na pasta de instalação.
