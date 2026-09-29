"""Linear queries used by startup orphan recovery."""

_IN_PROGRESS_QUERY = """
query InProgressPiCeoIssues($projectId: String!) {
    project(id: $projectId) {
        issues(filter: {
            state: { type: { in: ["started"] } }
        }, first: 30, orderBy: updatedAt) {
            nodes {
                id
                identifier
                title
                updatedAt
                state { name type }
                labels { nodes { name } }
                comments(first: 5, orderBy: createdAt) { nodes { body } }
            }
        }
    }
}
"""

_RECOVERY_TARGET_QUERY = """
query RecoveryTargetPiCeoIssues($projectId: String!, $targetState: String!) {
    project(id: $projectId) {
        issues(filter: {state: {name: {eq: $targetState}}},
               first: 30, orderBy: updatedAt) {
            nodes {
                id
                identifier
                state { name type }
                labels { nodes { name } }
                comments(first: 5, orderBy: createdAt) { nodes { body } }
            }
        }
    }
}
"""
