#!/bin/bash
# ---------------------------------------------------------------------------
# Dump evidence that a Codeface analysis actually populated the database.
#   collect_evidence.sh [project-name]
# ---------------------------------------------------------------------------
set -u
PROJECT=${1:-flask}
MYSQL="mysql -ucodeface -pcodeface codeface -t"

q() { echo; echo "### $1"; shift; $MYSQL -e "$*" 2>/dev/null; }

echo "==========================================================="
echo " Codeface database evidence  --  project: $PROJECT"
echo " generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "==========================================================="

q "Analysed projects" \
  "SELECT id, name, analysisMethod, analysisTime FROM project;"

q "Row counts across the populated tables" "
SELECT 'person' AS tbl, COUNT(*) AS rows_ FROM person
UNION ALL SELECT 'commit', COUNT(*) FROM commit
UNION ALL SELECT 'release_timeline', COUNT(*) FROM release_timeline
UNION ALL SELECT 'release_range', COUNT(*) FROM release_range
UNION ALL SELECT 'cluster', COUNT(*) FROM cluster
UNION ALL SELECT 'cluster_user_mapping', COUNT(*) FROM cluster_user_mapping
UNION ALL SELECT 'edgelist', COUNT(*) FROM edgelist
UNION ALL SELECT 'pagerank', COUNT(*) FROM pagerank
UNION ALL SELECT 'pagerank_matrix', COUNT(*) FROM pagerank_matrix
UNION ALL SELECT 'timeseries', COUNT(*) FROM timeseries
UNION ALL SELECT 'plots', COUNT(*) FROM plots
UNION ALL SELECT 'author_commit_stats', COUNT(*) FROM author_commit_stats
UNION ALL SELECT 'commit_dependency', COUNT(*) FROM commit_dependency
UNION ALL SELECT 'sloccount_ts', COUNT(*) FROM sloccount_ts
UNION ALL SELECT 'per_cluster_statistics', COUNT(*) FROM per_cluster_statistics
ORDER BY rows_ DESC;"

q "Release ranges analysed" "
SELECT rr.id AS range_id,
       r1.tag AS start_tag, r2.tag AS end_tag,
       (SELECT COUNT(*) FROM commit c WHERE c.releaseRangeId = rr.id) AS commits
FROM release_range rr
JOIN release_timeline r1 ON r1.id = rr.releaseStartId
JOIN release_timeline r2 ON r2.id = rr.releaseEndId
JOIN project p ON p.id = rr.projectId
WHERE p.name = '$PROJECT'
ORDER BY rr.id;"

q "Top 15 developers by commit count" "
SELECT pe.name, pe.email1, COUNT(*) AS commits
FROM commit c
JOIN person pe ON pe.id = c.author
JOIN project p ON p.id = c.projectId
WHERE p.name = '$PROJECT'
GROUP BY pe.id
ORDER BY commits DESC
LIMIT 15;"

q "Developer collaboration clusters per range (proximity tagging)" "
SELECT cl.releaseRangeId AS range_id,
       COUNT(DISTINCT cl.id)     AS clusters,
       COUNT(cum.personId)       AS cluster_memberships,
       COUNT(DISTINCT cum.personId) AS distinct_developers
FROM cluster cl
LEFT JOIN cluster_user_mapping cum ON cum.clusterId = cl.id
JOIN project p ON p.id = cl.projectId
WHERE p.name = '$PROJECT'
GROUP BY cl.releaseRangeId
ORDER BY cl.releaseRangeId;"

q "Most central developers by PageRank (top 10)" "
SELECT pe.name, pg.technique, pg.releaseRangeId AS range_id,
       ROUND(pr.rankValue, 6) AS pagerank
FROM pagerank_matrix pr
JOIN pagerank pg ON pg.id = pr.pageRankId
JOIN person pe   ON pe.id = pr.personId
JOIN project p   ON p.id = pe.projectId
WHERE p.name = '$PROJECT'
ORDER BY pr.rankValue DESC
LIMIT 10;"

q "Commit activity over time (per range)" "
SELECT c.releaseRangeId AS range_id,
       COUNT(*) AS commits,
       COUNT(DISTINCT c.author) AS distinct_authors,
       MIN(c.commitDate) AS first_commit,
       MAX(c.commitDate) AS last_commit,
       SUM(c.AddedLines) AS added, SUM(c.DeletedLines) AS deleted
FROM commit c JOIN project p ON p.id = c.projectId
WHERE p.name = '$PROJECT'
GROUP BY c.releaseRangeId ORDER BY c.releaseRangeId;"

q "Time series recorded" "
SELECT pl.name AS plot, pl.releaseRangeId AS range_id, COUNT(ts.time) AS points
FROM plots pl LEFT JOIN timeseries ts ON ts.plotId = pl.id
JOIN project p ON p.id = pl.projectId
WHERE p.name = '$PROJECT'
GROUP BY pl.id ORDER BY points DESC LIMIT 20;"

q "Complexity analysis: sloccount COCOMO estimates over time (latest 10)" "
SELECT DATE_FORMAT(s.time, '%Y-%m-%d') AS snapshot,
       ROUND(s.person_months, 1)       AS person_months,
       CONCAT('\$', FORMAT(s.total_cost, 0)) AS est_cost,
       ROUND(s.schedule_months, 1)     AS sched_months,
       ROUND(s.avg_devel, 2)           AS avg_devs
FROM sloccount_ts s
JOIN plots pl  ON pl.id = s.plotId
JOIN project p ON p.id = pl.projectId
WHERE p.name = '$PROJECT'
ORDER BY s.time DESC
LIMIT 10;"

q "Largest developer collaboration clusters" "
SELECT cl.releaseRangeId AS range_id, cl.clusterNumber AS cluster,
       COUNT(cum.personId) AS members,
       GROUP_CONCAT(pe.name ORDER BY pe.name SEPARATOR ', ') AS developers
FROM cluster cl
JOIN cluster_user_mapping cum ON cum.clusterId = cl.id
JOIN person pe  ON pe.id = cum.personId
JOIN project p  ON p.id = cl.projectId
WHERE p.name = '$PROJECT' AND cl.clusterNumber >= 0
GROUP BY cl.id
HAVING members > 2
ORDER BY members DESC
LIMIT 5;"

q "Per-cluster statistics" "
SELECT pcs.releaseRangeId AS range_id, pcs.clusterId, pcs.technique,
       pcs.num_members, pcs.numcommits, pcs.added, pcs.deleted,
       ROUND(pcs.prank_avg, 6) AS prank_avg
FROM per_cluster_statistics pcs
JOIN project p ON p.id = pcs.projectId
WHERE p.name = '$PROJECT'
ORDER BY pcs.releaseRangeId, pcs.num_members DESC
LIMIT 15;"

echo
echo "==========================================================="
