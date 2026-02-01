"""Bradley-Terry ranking model and pair selection algorithm."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import numpy as np

from src.models.item import Item
from src.models.vote import Vote
from src.models.settings import Settings


@dataclass
class RankingResult:
    """
    Result of ranking calculation for a single item.

    Attributes:
        item: The ranked item.
        strength: The raw Bradley-Terry strength parameter (pi).
        log_strength: The log of the strength parameter (s_i = log(pi)).
        elo_rating: The ELO-converted rating (centered at 1500).
        rank: The item's position in the ranking (1 = best).
        comparison_count: Total number of comparisons involving this item.
        log_strength_se: Standard error of log-strength from Fisher Information.
    """

    item: Item
    strength: float
    log_strength: float
    elo_rating: float
    rank: int
    comparison_count: int
    log_strength_se: float = 0.0


class BradleyTerryModel:
    """
    Bradley-Terry model for ranking items based on pairwise comparisons.

    The model estimates latent strength parameters for each item such that
    P(i beats j) = pi_i / (pi_i + pi_j).

    Uses the MM (Minorization-Maximization) algorithm with regularization
    to handle sparse comparison graphs.

    Attributes:
        items: List of items to rank.
        epsilon: Pseudo-count for regularization (default 0.01).
        max_iterations: Maximum MM algorithm iterations (default 10000).
        convergence_threshold: Convergence criterion for log-strength changes.

    Example:
        >>> model = BradleyTerryModel(items)
        >>> model.add_votes(votes)
        >>> results = model.compute_rankings()
    """

    def __init__(
        self,
        items: list[Item],
        epsilon: float = 0.01,
        max_iterations: int = 10000,
        convergence_threshold: float = 1e-10,
    ):
        """
        Initialize the Bradley-Terry model.

        Args:
            items: List of items to rank.
            epsilon: Pseudo-count added to all pairs for regularization.
            max_iterations: Maximum number of MM algorithm iterations.
            convergence_threshold: Stop when max log-strength change is below this.
        """
        self.items = list(items)
        self.epsilon = epsilon
        self.max_iterations = max_iterations
        self.convergence_threshold = convergence_threshold

        # Create item ID to index mapping
        self._id_to_idx: dict[str, int] = {
            item.id: i for i, item in enumerate(self.items)
        }

        # Initialize win matrix (will be populated by add_votes)
        n = len(self.items)
        self._win_matrix = np.zeros((n, n), dtype=np.float64)

        # Track actual comparison counts (separate from weighted win matrix)
        self._comparison_count = np.zeros(n, dtype=int)

        # Strength parameters (initialized in compute_rankings)
        self._strengths: Optional[np.ndarray] = None

    @property
    def n_items(self) -> int:
        """Return the number of items in the model."""
        return len(self.items)

    def add_votes(
        self,
        votes: list[Vote],
        decay_timescale_days: float = 0.0,
        reference_time: Optional[datetime] = None,
    ) -> None:
        """
        Add votes to the win matrix.

        Args:
            votes: List of Vote objects to add.
            decay_timescale_days: If > 0, apply time-based decay to vote weights.
            reference_time: Reference time for decay calculation. Defaults to now.
        """
        if reference_time is None:
            reference_time = datetime.now()

        for vote in votes:
            winner_idx = self._id_to_idx.get(vote.winner_id)
            loser_idx = self._id_to_idx.get(vote.loser_id)

            if winner_idx is None or loser_idx is None:
                # Skip votes involving unknown items
                continue

            # Track actual comparison count (before applying weight/decay)
            self._comparison_count[winner_idx] += 1
            self._comparison_count[loser_idx] += 1

            if decay_timescale_days > 0:
                weight = vote.get_decayed_weight(decay_timescale_days, reference_time)
            else:
                weight = vote.weight

            self._win_matrix[winner_idx, loser_idx] += weight

    def _apply_regularization(self) -> np.ndarray:
        """
        Apply regularization by adding epsilon to all off-diagonal entries.

        Returns:
            np.ndarray: Regularized win matrix.
        """
        n = self.n_items
        regularized = self._win_matrix.copy()

        # Add epsilon to all pairs (except diagonal)
        for i in range(n):
            for j in range(n):
                if i != j:
                    regularized[i, j] += self.epsilon

        return regularized

    def compute_rankings(self) -> list[RankingResult]:
        """
        Compute rankings using the MM algorithm.

        Returns:
            list[RankingResult]: List of ranking results sorted by rank (best first).

        Raises:
            ValueError: If there are fewer than 2 items to rank.
        """
        n = self.n_items
        if n < 2:
            if n == 1:
                return [RankingResult(
                    item=self.items[0],
                    strength=1.0,
                    log_strength=0.0,
                    elo_rating=1500.0,
                    rank=1,
                    comparison_count=0,
                )]
            return []

        # Apply regularization
        W = self._apply_regularization()

        # Initialize strengths to 1
        pi = np.ones(n, dtype=np.float64)

        # MM algorithm iteration
        for _ in range(self.max_iterations):
            pi_old = pi.copy()

            for i in range(n):
                # Total weighted wins for item i
                w_i = np.sum(W[i, :]) - W[i, i]

                # Denominator: sum over j != i of n_ij / (pi_i + pi_j)
                denom = 0.0
                for j in range(n):
                    if j != i:
                        n_ij = W[i, j] + W[j, i]
                        denom += n_ij / (pi[i] + pi[j])

                if denom > 0:
                    pi[i] = w_i / denom

            # Normalize to geometric mean = 1
            log_mean = np.mean(np.log(pi + 1e-300))  # Avoid log(0)
            pi = pi / np.exp(log_mean)

            # Check convergence
            log_diff = np.abs(np.log(pi + 1e-300) - np.log(pi_old + 1e-300))
            if np.max(log_diff) < self.convergence_threshold:
                break

        self._strengths = pi

        # Convert to ELO ratings
        elo_ratings = self._compute_elo_ratings(pi)

        # Count comparisons per item
        comparison_counts = self._count_comparisons()

        # Compute standard errors of log-strength
        log_strength_ses = self._compute_log_strength_standard_errors(pi)

        # Build results
        results = []
        for i, item in enumerate(self.items):
            results.append(RankingResult(
                item=item,
                strength=pi[i],
                log_strength=np.log(pi[i]) if pi[i] > 0 else float('-inf'),
                elo_rating=elo_ratings[i],
                rank=0,  # Will be set after sorting
                comparison_count=comparison_counts[i],
                log_strength_se=log_strength_ses[i],
            ))

        # Sort by strength (descending) and assign ranks
        results.sort(key=lambda r: r.strength, reverse=True)
        for rank, result in enumerate(results, start=1):
            result.rank = rank

        return results

    def _compute_elo_ratings(self, pi: np.ndarray) -> np.ndarray:
        """
        Convert strength parameters to ELO ratings.

        Uses z-score normalization: rating = 1500 + z * 200

        Args:
            pi: Array of strength parameters.

        Returns:
            np.ndarray: Array of ELO ratings.
        """
        s = np.log(pi + 1e-300)  # log-strengths

        mean_s = np.mean(s)
        std_s = np.std(s)

        if std_s < 1e-10:
            # All items have same strength, give them all 1500
            return np.full_like(s, 1500.0)

        z = (s - mean_s) / std_s
        return 1500.0 + z * 200.0

    def _count_comparisons(self) -> list[int]:
        """
        Count total comparisons involving each item.

        Returns:
            list[int]: List of comparison counts per item.
        """
        return self._comparison_count.tolist()

    def _compute_fisher_information(self, pi: np.ndarray) -> np.ndarray:
        """
        Compute the Fisher Information matrix for log-strength parameters.

        Fisher Information matrix elements use p_ij * (1-p_ij) weighting:
        - Diagonal: I_ii = Σ_{k≠i} n_ik * π_i * π_k / (π_i + π_k)²
        - Off-diagonal: I_ij = -n_ij * π_i * π_j / (π_i + π_j)²

        Where n_ij = W[i,j] + W[j,i] (total comparisons between i and j).
        The π_i * π_j / (π_i + π_j)² term equals p_ij * (1-p_ij), reflecting
        that comparisons between evenly-matched items are more informative.

        Args:
            pi: Array of strength parameters.

        Returns:
            np.ndarray: Fisher Information matrix (n x n).
        """
        n = self.n_items
        W = self._apply_regularization()
        I = np.zeros((n, n), dtype=np.float64)

        for i in range(n):
            for j in range(n):
                if i == j:
                    # Diagonal: sum over all k != i
                    for k in range(n):
                        if k != i:
                            n_ik = W[i, k] + W[k, i]
                            pq = pi[i] * pi[k] / (pi[i] + pi[k]) ** 2
                            I[i, i] += n_ik * pq
                else:
                    # Off-diagonal
                    n_ij = W[i, j] + W[j, i]
                    pq = pi[i] * pi[j] / (pi[i] + pi[j]) ** 2
                    I[i, j] = -n_ij * pq

        return I

    def _compute_log_strength_standard_errors(self, pi: np.ndarray) -> np.ndarray:
        """
        Compute standard errors of log-strength estimates.

        Uses the inverse of the Fisher Information matrix:
        SE(log π_i) = √[(I⁻¹)_ii]

        Args:
            pi: Array of strength parameters.

        Returns:
            np.ndarray: Array of standard errors for each item.
        """
        n = self.n_items
        if n < 2:
            return np.zeros(n, dtype=np.float64)

        I = self._compute_fisher_information(pi)

        # Use pseudo-inverse since Fisher Information is rank n-1 (normalization constraint)
        I_inv = np.linalg.pinv(I)
        # Extract diagonal and take square root for standard errors
        variances = np.diag(I_inv)
        # Handle any negative values (numerical issues)
        variances = np.maximum(variances, 0.0)
        return np.sqrt(variances)

    def get_win_probability(self, item_a_id: str, item_b_id: str) -> float:
        """
        Get the probability that item A beats item B.

        Args:
            item_a_id: ID of item A.
            item_b_id: ID of item B.

        Returns:
            float: Probability that A beats B, or 0.5 if items not found.
        """
        if self._strengths is None:
            return 0.5

        idx_a = self._id_to_idx.get(item_a_id)
        idx_b = self._id_to_idx.get(item_b_id)

        if idx_a is None or idx_b is None:
            return 0.5

        pi_a = self._strengths[idx_a]
        pi_b = self._strengths[idx_b]

        return pi_a / (pi_a + pi_b)


class PairSelector:
    """
    Selects the next pair of items to compare.

    Balances multiple factors:
    - Uncertainty: Prefer pairs with close ratings (more informative)
    - Connectivity: Prefer pairs that connect disconnected components
    - Freshness: Prefer pairs with stale/decayed votes
    - Uncompared: Strongly prefer items with no comparisons
    - Top-tier: Optionally prioritize top-ranked items

    Example:
        >>> selector = PairSelector(items, votes, settings)
        >>> item_a, item_b = selector.select_pair(rankings)
    """

    def __init__(
        self,
        items: list[Item],
        votes: list[Vote],
        settings: Settings,
    ):
        """
        Initialize the pair selector.

        Args:
            items: List of all items.
            votes: List of all votes.
            settings: Application settings with selection weights.
        """
        self.items = list(items)
        self.votes = list(votes)
        self.settings = settings

        # Build item ID to index mapping
        self._id_to_idx = {item.id: i for i, item in enumerate(self.items)}

        # Build vote data structures
        self._build_vote_structures()

    def _build_vote_structures(self) -> None:
        """Build data structures for efficient pair scoring."""
        n = len(self.items)

        # Count comparisons per pair
        self._pair_comparison_count: dict[frozenset, int] = {}

        # Most recent vote time per pair
        self._pair_last_vote: dict[frozenset, datetime] = {}

        # Total comparisons per item
        self._item_comparison_count = [0] * n

        for vote in self.votes:
            pair = vote.get_pair_unordered()

            # Increment pair count
            self._pair_comparison_count[pair] = self._pair_comparison_count.get(pair, 0) + 1

            # Update last vote time
            existing = self._pair_last_vote.get(pair)
            if existing is None or vote.timestamp > existing:
                self._pair_last_vote[pair] = vote.timestamp

            # Increment item counts
            winner_idx = self._id_to_idx.get(vote.winner_id)
            loser_idx = self._id_to_idx.get(vote.loser_id)
            if winner_idx is not None:
                self._item_comparison_count[winner_idx] += 1
            if loser_idx is not None:
                self._item_comparison_count[loser_idx] += 1

    def _find_connected_components(self) -> list[set[int]]:
        """
        Find connected components in the comparison graph.

        Returns:
            list[set[int]]: List of sets, each containing item indices in a component.
        """
        n = len(self.items)
        visited = [False] * n
        components = []

        def dfs(node: int, component: set[int]):
            visited[node] = True
            component.add(node)

            # Find neighbors (items that have been compared with this one)
            for vote in self.votes:
                pair = vote.get_pair_unordered()
                item_ids = list(pair)

                if len(item_ids) != 2:
                    continue

                idx0 = self._id_to_idx.get(item_ids[0])
                idx1 = self._id_to_idx.get(item_ids[1])

                if idx0 is None or idx1 is None:
                    continue

                if idx0 == node and not visited[idx1]:
                    dfs(idx1, component)
                elif idx1 == node and not visited[idx0]:
                    dfs(idx0, component)

        for i in range(n):
            if not visited[i]:
                component: set[int] = set()
                dfs(i, component)
                components.append(component)

        return components

    def _score_pair(
        self,
        idx_a: int,
        idx_b: int,
        rankings: Optional[list[RankingResult]],
        components: list[set[int]],
        now: datetime,
    ) -> float:
        """
        Calculate priority score for a pair (higher = more priority).

        Args:
            idx_a: Index of first item.
            idx_b: Index of second item.
            rankings: Current ranking results (if available).
            components: Connected components in comparison graph.
            now: Current time for freshness calculation.

        Returns:
            float: Priority score for this pair.
        """
        item_a = self.items[idx_a]
        item_b = self.items[idx_b]
        pair = frozenset([item_a.id, item_b.id])

        score = 0.0

        # 1. Uncertainty score: prefer pairs with high estimation uncertainty
        # Uses sum of standard errors from Bradley-Terry Fisher Information
        if rankings and self.settings.weight_uncertainty > 0:
            se_a = next((r.log_strength_se for r in rankings if r.item.id == item_a.id), 1.0)
            se_b = next((r.log_strength_se for r in rankings if r.item.id == item_b.id), 1.0)
            # Higher combined SE = higher uncertainty = higher priority
            uncertainty_score = se_a + se_b
            score += self.settings.weight_uncertainty * uncertainty_score

        # 2. Connectivity score: prefer pairs that connect different components
        if self.settings.weight_connectivity > 0:
            component_a = None
            component_b = None
            for comp in components:
                if idx_a in comp:
                    component_a = comp
                if idx_b in comp:
                    component_b = comp

            if component_a is not None and component_b is not None and component_a != component_b:
                # This pair would connect two components - high priority
                score += self.settings.weight_connectivity * 10.0

        # 3. Freshness score: prefer pairs with stale votes
        if self.settings.weight_freshness > 0:
            last_vote = self._pair_last_vote.get(pair)
            if last_vote is not None:
                days_since = (now - last_vote).total_seconds() / 86400.0
                # Score increases with age, scaled by decay timescale
                if self.settings.decay_timescale_days > 0:
                    freshness_score = days_since / self.settings.decay_timescale_days
                    score += self.settings.weight_freshness * min(freshness_score, 5.0)

        # 4. Uncompared priority: strongly prefer items with no comparisons
        if self.settings.weight_uncompared > 0:
            count_a = self._item_comparison_count[idx_a]
            count_b = self._item_comparison_count[idx_b]

            if count_a == 0 or count_b == 0:
                # At least one item has never been compared - very high priority
                score += self.settings.weight_uncompared * 10.0
            elif count_a < 3 or count_b < 3:
                # Few comparisons - moderate boost
                score += self.settings.weight_uncompared * 3.0

            # Also prefer pairs that haven't been compared directly
            pair_count = self._pair_comparison_count.get(pair, 0)
            if pair_count == 0:
                score += self.settings.weight_uncompared * 1.5

        # 5. Top-tier focus: prefer comparisons involving top items
        if self.settings.top_tier_mode and rankings:
            top_n = self.settings.top_tier_count

            rank_a = next((r.rank for r in rankings if r.item.id == item_a.id), len(rankings))
            rank_b = next((r.rank for r in rankings if r.item.id == item_b.id), len(rankings))

            is_top_a = rank_a <= top_n
            is_top_b = rank_b <= top_n

            if is_top_a and is_top_b:
                # Both in top tier - highest priority
                score += self.settings.top_tier_weight * 3.0
            elif is_top_a or is_top_b:
                # One in top tier - check if other could be a "riser"
                other_rank = rank_b if is_top_a else rank_a
                # "Potential riser" = within 2x of top tier threshold
                if other_rank <= top_n * 2:
                    score += self.settings.top_tier_weight * 1.5
                else:
                    score += self.settings.top_tier_weight * 0.5

        return score

    def select_pair(
        self,
        rankings: Optional[list[RankingResult]] = None,
    ) -> Optional[tuple[Item, Item]]:
        """
        Select the best pair of items to compare next.

        Args:
            rankings: Current ranking results. If None, uses default ordering.

        Returns:
            tuple[Item, Item]: The selected pair, or None if < 2 items exist.
        """
        n = len(self.items)
        if n < 2:
            return None

        # Find connected components
        components = self._find_connected_components()

        now = datetime.now()

        # Score all pairs
        best_pair: Optional[tuple[int, int]] = None
        best_score = float('-inf')

        for i in range(n):
            for j in range(i + 1, n):
                pair_score = self._score_pair(i, j, rankings, components, now)

                if pair_score > best_score:
                    best_score = pair_score
                    best_pair = (i, j)

        if best_pair is None:
            # Fallback: return first two items
            return (self.items[0], self.items[1])

        return (self.items[best_pair[0]], self.items[best_pair[1]])

    def get_comparison_stats(self) -> dict:
        """
        Get statistics about comparisons.

        Returns:
            dict: Statistics including total votes, items compared, etc.
        """
        n = len(self.items)
        total_pairs = n * (n - 1) // 2
        compared_pairs = len(self._pair_comparison_count)
        uncompared_items = sum(1 for c in self._item_comparison_count if c == 0)

        return {
            "total_items": n,
            "total_possible_pairs": total_pairs,
            "compared_pairs": compared_pairs,
            "uncompared_pairs": total_pairs - compared_pairs,
            "total_votes": len(self.votes),
            "uncompared_items": uncompared_items,
        }
