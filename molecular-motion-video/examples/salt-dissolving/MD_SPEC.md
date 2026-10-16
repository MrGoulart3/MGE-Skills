# Dinâmica molecular para o vídeo "Salt dissolving" (contrato de dados)

Objetivo: uma trajetória REAL e fisicamente plausível de um nanocristal de NaCl em água em que íons do canto/aresta se soltam e saem hidratados. Ela guia o movimento no Blender.

## Sistema
- Nanocristal de rocksalt: NaCl 4×4×4 (64 íons, a = 5,64 Å), neutro, centrado numa caixa cúbica de água (≥ 12 Å de água além do cristal em cada lado; ~2000–2600 TIP3P ou TIP4P-Ew).
- Campo de força: íons de Joung–Cheatham ajustados ao modelo de água escolhido (preferir OpenMM + `amber14/tip3p.xml` ou equivalente com parâmetros JC). PME, corte 10 Å, H com restrição (rígida), passo 2 fs.
- Minimização → NVT 100 ps → NPT 1 bar (100–200 ps) → produção NVT.
- **Acelerar a dissolução de forma legítima**: produção a 350–400 K (ou 300 K com SMD suave puxando 1 Na⁺ e 1 Cl⁻ de quina para fora, força constante pequena). Objetivo: ≥ 2 íons totalmente solvatados (fora da 1ª camada do cristal, distância ao íon mais próximo do cristal > 5 Å) dentro da janela salva. Documente a escolha (temperatura/SMD) — o vídeo é ilustrativo, mas os dados devem ser honestos.
- Duração: o que for preciso para ≥ 2 eventos de saída (estimativa 2–10 ns a 350–400 K). Salvar a cada 0,5–1 ps só a JANELA útil final (ex.: 200–400 ps ao redor dos eventos), mais 50 ps iniciais de "cristal intacto".

## Execução
- Execução local ou remota conforme os recursos disponíveis. Em recursos compartilhados, siga a alocação do administrador ou do escalonador; não interrompa jobs de outras pessoas.
- `md/md_sal.py` usa `NT` (compatibilidade) ou `MMV_THREADS`, nessa ordem, com padrão de 4 threads. No runner remoto, configure `threads` (padrão 4) e `max_cpu_percent` (padrão 60, teste de admissão por carga média apenas para `scheduler: none`) em `cluster.yaml`. Não há horários ou limites particulares de máquina.
- Ambiente: reutilize um ambiente compatível do projeto ou crie um dedicado com `env/environment-calc.yml`. Ajuste o orçamento de recursos antes de executar cálculos ou renders.

## Saída obrigatória (`md/` (relativo à pasta deste exemplo))
- `traj.npz` com:
  - `positions` float32 (F, N, 3) em Å, **desdobrados** (moléculas inteiras, sem saltos de PBC), com o centro do cristal remanescente fixo na origem;
  - `time_ps` (F,);
  - `element` (N,) str em {"Na","Cl","O","H"};
  - `molecule` (N,) int (id da molécula de água; íons com id próprio);
  - `box` (3,) Å.
- **Recorte**: mantenha todos os íons e só as águas que, em algum frame, ficam a < 14 Å de algum íon do cristal ou dos íons que saem (para o Blender não carregar milhares de moléculas inúteis). Remova sítios virtuais (TIP4P M).
- `events.json`: lista de eventos com `{"kind": "detach", "ion": "Na"|"Cl", "index": i, "frame": f, "time_ps": t}` (frame em que o íon passa a > 5 Å do cristal) e, por íon que sai, a contagem de águas na 1ª camada (Na–O < 3,2 Å; Cl–H < 2,9 Å) ao longo dos frames (`hydration` como lista).
- `DATA_README.md` curto: versões, parâmetros, temperatura/SMD, quantos ns, eventos encontrados, validações (densidade da água ~1, distância Na–Cl no cristal ~2,8 Å, número de coordenação Na–O ~5–6 e Cl–O ~6–7 para íons livres).
