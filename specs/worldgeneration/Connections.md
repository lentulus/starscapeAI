Key thresholds:

jump	components	isolates	giant
3 pc	7.2M	6.3M	0.03%
6 pc	2.3M	1.5M	33.5% ← percolation transition
7 pc	1.2M	769K	62.8%
10 pc	232K	163K	93.9%
20 pc	~16	~14	100.00%
100 pc	2	0	100.00%
At max jump-6 (Traveller standard): only a third of stars are reachable from any given system. The giant component percolates sharply between 5 and 6 pc — classic phase transition behaviour.

At jump-10: 94% coverage, ~164K isolated stars remain.

Full connectivity: 2 components remain at 100 pc — two star(s) or small clusters that are genuinely isolated from the main body. Need --max-pc 200 or --knn 80 to find the exact bridging distance. The giant component hits 100.00% (rounded) at ~20 pc, so those 2 remaining components are tiny outliers far from the bulk.

Implication for the sim: species starting within the dense solar neighbourhood are well-connected at jump-6, but roughly two-thirds of the catalog is unreachable at that range. The simulation's expansion will naturally be confined to the dense inner region.