#include <iostream>
#include <vector>
#include <string>
#include <algorithm>
#include <map>

using namespace std;

const long long MOD = 1e9 + 7;

struct Node {
    long long sum;
    int left, right;
};

vector<Node> tree;
int node_count;

int build(int l, int r) {
    int curr = ++node_count;
    tree[curr].sum = 0;
    if (l == r) {
        tree[curr].left = tree[curr].right = 0;
        return curr;
    }
    int mid = l + (r - l) / 2;
    tree[curr].left = build(l, mid);
    tree[curr].right = build(mid + 1, r);
    return curr;
}

int update(int prev, int l, int r, int pos, long long val) {
    int curr = ++node_count;
    tree[curr] = tree[prev];
    tree[curr].sum = (tree[curr].sum + val) % MOD;
    if (l == r) {
        return curr;
    }
    int mid = l + (r - l) / 2;
    if (pos <= mid) {
        tree[curr].left = update(tree[prev].left, l, mid, pos, val);
    } else {
        tree[curr].right = update(tree[prev].right, mid + 1, r, pos, val);
    }
    return curr;
}

long long query(int curr, int l, int r, int ql, int qr) {
    if (!curr || ql > qr || l > qr || r < ql) {
        return 0;
    }
    if (ql <= l && r <= qr) {
        return tree[curr].sum;
    }
    int mid = l + (r - l) / 2;
    long long res = (query(tree[curr].left, l, mid, ql, qr) + query(tree[curr].right, mid + 1, r, ql, qr)) % MOD;
    return res;
}

int main() {
    ios_base::sync_with_stdio(false);
    cin.tie(NULL);

    int n;
    cin >> n;
    string s;
    cin >> s;

    vector<int> lastR(n + 1, 0);
    for (int i = 1; i <= n; ++i) {
        lastR[i] = lastR[i - 1];
        if (s[i - 1] == 'R') {
            lastR[i] = i;
        }
    }

    vector<int> nextB(n + 2, n + 1);
    for (int i = n; i >= 1; --i) {
        nextB[i] = (s[i - 1] == 'B') ? i : nextB[i + 1];
    }

    vector<long long> imax(n + 1);
    vector<long long> imax_coords;
    imax_coords.reserve(n + 1);
    for (int p = 0; p <= n; ++p) {
        long long k_max = nextB[p + 1] - 1;
        imax[p] = 2 * k_max - p;
        imax_coords.push_back(imax[p]);
    }

    sort(imax_coords.begin(), imax_coords.end());
    imax_coords.erase(unique(imax_coords.begin(), imax_coords.end()), imax_coords.end());

    auto get_coord_idx = [&](long long val) {
        return lower_bound(imax_coords.begin(), imax_coords.end(), val) - imax_coords.begin();
    };

    int C = imax_coords.size();
    if (C == 0) C = 1;
    tree.resize(2 * C + n * 20); 
    node_count = 0;

    vector<int> even_roots(n + 1, 0);
    vector<int> odd_roots(n + 1, 0);
    int empty_root = build(0, C - 1);
    for(int i = 0; i <= n; ++i) {
        even_roots[i] = odd_roots[i] = empty_root;
    }

    vector<long long> dp(n + 1, 0);
    dp[0] = 1;

    int imax0_coord = get_coord_idx(imax[0]);
    even_roots[0] = update(empty_root, 0, C - 1, imax0_coord, dp[0]);

    for (int i = 1; i <= n; ++i) {
        even_roots[i] = even_roots[i-1];
        odd_roots[i] = odd_roots[i-1];

        long long h_i = 2LL * lastR[i] - i;
        int p_min = max(0LL, h_i - 1);
        int p_max = i - 2;

        long long S_i = 0;
        int coord_idx_i = get_coord_idx(i);

        if (p_min <= p_max) {
            if (i % 2 == 0) { // p needs to be even
                int p_start = p_min;
                if (p_start % 2 != 0) p_start++;
                int p_end = p_max;
                if (p_end % 2 != 0) p_end--;

                if (p_start <= p_end) {
                    int root_end = even_roots[p_end];
                    int root_start = (p_start > 0) ? even_roots[p_start - 1] : empty_root;
                    long long total_sum = query(root_end, 0, C - 1, coord_idx_i, C - 1);
                    long long prefix_sum = query(root_start, 0, C - 1, coord_idx_i, C - 1);
                    S_i = (total_sum - prefix_sum + MOD) % MOD;
                }
            } else { // p needs to be odd
                int p_start = p_min;
                if (p_start % 2 == 0) p_start++;
                int p_end = p_max;
                if (p_end % 2 == 0) p_end--;

                if (p_start <= p_end) {
                    int root_end = odd_roots[p_end];
                    int root_start = (p_start > 0) ? odd_roots[p_start - 1] : empty_root;
                    long long total_sum = query(root_end, 0, C - 1, coord_idx_i, C - 1);
                    long long prefix_sum = query(root_start, 0, C - 1, coord_idx_i, C - 1);
                    S_i = (total_sum - prefix_sum + MOD) % MOD;
                }
            }
        }

        dp[i] = S_i;
        if (s[i - 1] == 'X') {
            dp[i] = (dp[i] + dp[i - 1]) % MOD;
        }

        if (dp[i] > 0) {
            int imax_i_coord = get_coord_idx(imax[i]);
            if (i % 2 == 0) {
                even_roots[i] = update(even_roots[i], 0, C - 1, imax_i_coord, dp[i]);
            } else {
                odd_roots[i] = update(odd_roots[i], 0, C - 1, imax_i_coord, dp[i]);
            }
        }
    }

    cout << dp[n] << endl;

    return 0;
}
