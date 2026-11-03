# UniRota

Sistema web para apoiar a gestão de rotas e do transporte universitário. O projeto é desenvolvido com Django e organiza suas funcionalidades em aplicativos independentes.

## Estrutura

```text
sistema-unirotas/
├── authentication/   # Autenticação, cadastro, conta e notificações
├── core/             # Configurações e inicialização do Django
├── management/       # Aplicativo de gestão
├── metrics/          # Aplicativo de métricas
├── operation/        # Aplicativo de operações
├── media/            # Arquivos enviados pela aplicação, como imagens de ônibus
├── static/           # Recursos estáticos compartilhados
├── templates/        # Templates compartilhados, incluindo recuperação de senha
└── requirements.txt  # Dependências Python
```

Os aplicativos `authentication`, `management`, `metrics` e `operation` possuem diretórios de migrações. O app de autenticação também contém templates, estilos e imagens próprios.

## Tecnologias

As dependências listadas em `requirements.txt` incluem:

- Django 6.1.1
- Pillow 12.3.0
- asgiref 3.12.1
- sqlparse 0.6.0

## Requisitos

- Python compatível com a versão do Django definida em `requirements.txt`
- `pip`

## Configuração local no Windows

No PowerShell, na raiz do projeto:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Se a ativação do ambiente virtual for bloqueada pelo PowerShell, consulte as políticas de execução do seu ambiente ou use o Prompt de Comando:

```bat
.venv\Scripts\activate.bat
```

## Banco de dados e migrações

Aplique as migrações dos aplicativos:

```powershell
python manage.py migrate
```

Para criar um usuário administrador, se necessário:

```powershell
python manage.py createsuperuser
```

## Executar o projeto

Inicie o servidor de desenvolvimento:

```powershell
python manage.py runserver
```

A aplicação ficará disponível em <http://127.0.0.1:8000/>.

## Testes

Execute os testes automatizados:

```powershell
python manage.py test
```

## Arquivos estáticos e mídia

O projeto contém recursos estáticos em `static/` e arquivos de mídia em `media/`. Em produção, configure o servidor e as definições do Django para servir esses arquivos de acordo com o ambiente.
