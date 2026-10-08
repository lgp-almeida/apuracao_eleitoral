# Roteiro — testar o front-end novo com os dados reais (08/10/2026)

O que fazer, à mão, para conferir a página do ramo `frontend-refatoracao` (rodadas 60–69) antes do merge em
`main`, que fica para depois do 2º turno (25/10). Os testes automáticos já passam: 134 Vitest e 493 pytest, dos
quais 80 são e2e. O ensaio geral também passou com um navegador acompanhando
([RODADA_69](RODADA_69_2026-10-08_frontend_fase6_limpeza.md)). Falta o olho de quem usa o site, com os dados de
verdade. Pendência registrada no [TODO 29](TODO.md).

**Não precisa de Node.** A página compilada (`apuracao/web/static/`) está no próprio ramo.

## 1. Preparar

```bash
cd /prj/prjatrv/lgonzaga/DVLP/apuracao_eleitoral
git fetch && git checkout frontend-refatoracao && git pull
source venv/bin/activate
```

- **Sites já no ar nesta pasta (8000, 8001):** eles leem `static/` do disco, então passam a mostrar a página do ramo
  em que a pasta estiver. Recarregue com Ctrl+F5. O Python deles continua o da hora em que subiram.
- **Não rode `npm run build` com um site no ar:** o build apaga os arquivos antigos de `static/assets/`.
- **Use portas livres (8077, 8078…)** para não disputar com os sites que estão no ar.

## 2. Os quatro jeitos de subir

| # | Para quê | Comando | Abrir |
|---|---|---|---|
| A | 1º turno de 2026 (dados reais coletados na noite) | `python site_apuracao.py --dados dados_2026/oficial --porta 8077` | http://localhost:8077 |
| B | Apuração andando (ensaio: RJ 2022 acelerado) | `python ensaio_apuracao.py --velocidade 60 --manter` (~7 min; sem `--velocidade` ~14 min) | http://localhost:8040 |
| C | Várias UFs, com seletor | `python site_apuracao.py --ufs todas --dados dados_2026/historico_2022_t1 --porta 8078` | http://localhost:8078/rj/ |
| D | 2º turno (ES 2022) | `python ensaio_apuracao.py --uf ES --turno 2 --velocidade 60 --manter` | http://localhost:8040 |

Ctrl+C encerra cada um. Com `--manter`, o ensaio deixa o site no ar ao fim, para olhar o resultado final com calma.

## 3. O que conferir

Marque o que der certo e anote o que não der, como pedido no item 5.

### Em todo lugar (A)

- [ ] **Régua de apuração** sob o cabeçalho: % das seções da UF, hora da última totalização e "final" no fim.
- [ ] **Tema:** o seletor "Tema" do cabeçalho troca claro/escuro/sistema e a escolha fica depois de recarregar.
  `http://localhost:8077/?tema=escuro#painel` força o escuro (o `?tema=` vem **antes** do `#`).
- [ ] **Abas pelo teclado:** clique numa aba e use ←/→, Home e End. O foco fica visível.
- [ ] **Copiar link** em cada aba: colar o link em outra janela abre o mesmo estado.
- [ ] **Nenhum erro no console** do navegador (F12 → Console) ao passar por todas as abas.

### Aba a aba (A)

- [ ] **Painel:** cartões dos cargos, projeção, cadeiras de deputado e destaque de partidos (`#painel?destacar=`).
  No cartão Brasil, o bloco **"Por estado"** com o mapa, a tabela e a dica de cada UF.
- [ ] **Mapas:** troca de cargo, métrica e candidato; Detalhe "Bairros", "Locais de votação" e "Áreas de
  ponderação" com as camadas; o "como estava às HH:MM"; a exportação PNG/SVG.
- [ ] **Candidato:** busca, tabela por município ordenável, planilha e "Resultado por município × eleição anterior".
- [ ] **Comparação** (2026 × 2022): métricas, gráfico da variação por partido e bancadas.
- [ ] **Perfil** e **1º → 2º turno**: um cálculo de cada.

### Casos que já quebraram (A)

- [ ] Abra o site **direto em `#mapas`** e só depois vá ao Painel. O mapa "Por estado" deve aparecer enquadrado.
  Esse era o defeito corrigido na rodada 69.
- [ ] **Celular:** no modo responsivo do navegador (F12 → ícone de celular), largura de 360 px. Nenhuma aba pode
  rolar para o lado.

### Com a apuração andando (B e D)

- [ ] A régua sobe de ~0% até 100% e marca o final.
- [ ] O painel se atualiza sozinho a cada minuto, sem piscar e sem perder a aba ou o cargo escolhido.
- [ ] **Modo TV:** `#painel?tv=1` roda um cartão por vez a cada 20 s. Esc sai; ←/→ e espaço navegam.
- [ ] **Alertas:** botão "Acompanhar", faixa de avisos e som.
- [ ] No 2º turno (D): a projeção diz "vitória projetada", e a aba 1º → 2º turno funciona.

### Várias UFs (C)

- [ ] O seletor de UF do cabeçalho troca de `/rj/` para outra UF e a página carrega inteira (régua, fonte e mapas).

## 4. Comparar com a página antiga (opcional)

Para ver as duas lado a lado, crie uma segunda cópia da pasta no `main`:

```bash
git worktree add ../apuracao_main main
cd ../apuracao_main && ../apuracao_eleitoral/venv/bin/python site_apuracao.py \
  --dados ../apuracao_eleitoral/dados_2026/oficial --cache-dir ../apuracao_eleitoral/cache_tse --porta 8066
```

http://localhost:8066 mostra a página antiga e http://localhost:8077 a nova. Os dados e o cache não estão no git:
por isso os caminhos apontam para a pasta original. Para apagar a cópia: `git worktree remove ../apuracao_main`.

## 5. Se achar um problema

Anote, para cada um:

- o endereço completo (com o `#...`);
- o tema, a largura da janela e o navegador;
- o que esperava e o que aconteceu (uma captura de tela ajuda);
- o erro do console, se houver.

A correção é feita no ramo `frontend-refatoracao`, com um teste que reproduz o caso.

## 6. Pronto quando

- todos os itens acima marcados ou com problema anotado e corrigido;
- então o [TODO 29](TODO.md) é fechado, e o merge em `main` segue o [TODO 27](TODO.md): depois de 25/10, com
  `pytest -q` e o ensaio de novo no `main` atualizado.

## 7. Voltar à página antiga

`git checkout main` volta tudo à página antiga (o `app.js` em `static/`). Os sites no ar mostram a página antiga
depois do Ctrl+F5.
