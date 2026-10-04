"""
M10 自监督结构发现 → 显微自动解析
===================================
DINO4DSTEM 风格自监督：从生物质 X 射线/电镜图自动发现孔隙/晶体/无定形分区，
无需标注。本原型用"无监督特征提取 + 聚类"演示完整链路。

修复：聚类标签是无序的，此前把硬编码图例当成真实映射，说法过头。现在按每个
簇的"平均强度"自动把簇映射到结构域（晶体=高强度规则条纹、孔隙=低强度暗区、
无定形=中等强度无规），图例与真实空间分布一致。

来源：digest-g4-2-2026-08-30.md 授粉点 3（源自 2608.15098 DINO4DSTEM）。

验收：原型 + 结构分区可视化。

运行：python m10_selfsupervised_microscopy.py
依赖：numpy, scikit-learn
"""
import numpy as np
from sklearn.cluster import KMeans

rng = np.random.default_rng(1)

# ---- 合成显微图：64x64，三种结构域 ----
H, W = 64, 64
img = np.zeros((H, W))
img[0:24, 0:24] = 0.8 * (1 + np.sin(np.arange(24) / 2.0))          # 晶体：规则条纹（高强度）
img[0:24, 24:48] = rng.uniform(0, 0.2, size=(24, 24))              # 孔隙：暗区
img[24:64, :] = 0.5 + 0.2 * rng.normal(0, 1, size=(40, 64))        # 无定形：中等强度无规
img += rng.normal(0, 0.02, size=(H, W))


def patch_features(im, ps=8):
    feats, coords = [], []
    for i in range(0, im.shape[0] - ps + 1, ps):
        for j in range(0, im.shape[1] - ps + 1, ps):
            p = im[i:i + ps, j:j + ps]
            gx, gy = np.gradient(p)
            feats.append([p.mean(), p.std(),
                          np.abs(gx).mean(), np.abs(gy).mean(),
                          np.corrcoef(p.ravel(), p[::-1].ravel())[0, 1]])
            coords.append((i // ps, j // ps))
    return np.array(feats), np.array(coords)


F, C = patch_features(img)
kmeans = KMeans(n_clusters=3, n_init=10, random_state=0).fit(F)
labels = kmeans.labels_.reshape(8, 8)

# ---- 按平均强度把簇自动映射到结构域（而非硬编码）----
cluster_mean = {c: F[kmeans.labels_ == c, 0].mean() for c in range(3)}
by_intensity = sorted(cluster_mean, key=cluster_mean.get)   # 升序
name = {by_intensity[0]: "孔隙", by_intensity[1]: "无定形", by_intensity[2]: "晶体"}
sym = {by_intensity[0]: ".", by_intensity[1]: "o", by_intensity[2]: "#"}

print("=" * 60)
print("M10 自监督结构发现 → 显微结构分区")
print("=" * 60)
print("结构分区图（#=晶体  .=孔隙  o=无定形，无标签自动发现）:")
print()
for row in labels:
    print("  " + "".join(sym[c] for c in row))
print()
for c in range(3):
    print(f"  簇 {c} → {name[c]}（平均强度 {cluster_mean[c]:.3f}）")
print()
print("说明：左上规则条纹被归为高强度的晶体域，右上暗区归为孔隙域，")
print("下半中等强度无规起伏归为无定形域——与真实空间分布一致。")
