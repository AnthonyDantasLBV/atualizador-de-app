# django-app-update-guard

App Django para atualização obrigatória de apps Android distribuídos fora da Play Store: publicação do APK pelo Django Admin, versão exigida, bloqueio HTTP 426 nas rotas do app (Django REST Framework), links pessoais de download e página de download com usuário e senha.

Funciona em conjunto com o plugin Flutter [`app_update_guard`](../flutter/).

Instalação, configuração e uso: veja o [README principal](../README.md#parte-1--django).

```bash
pip install "git+<URL-DO-REPOSITORIO>#subdirectory=django"
```

Testes:

```bash
python runtests.py
```
