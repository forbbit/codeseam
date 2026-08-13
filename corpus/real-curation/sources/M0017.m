function [tsComb, info] = combineCenters(tsCell, opts)
%COMBINECENTERS VCE-weighted combination of multi-center monthly series.
%
%   [TSCOMB, INFO] = shLowLevel.combineCenters({tsITSG, tsCSR, tsGFZ}) combines
%   monthly solutions from several processing centers into one series
%   with one variance factor per (center, month), estimated by Foerstner
%   variance-component iteration with PARTIAL REDUNDANCIES:
%
%       x^(t)      = ( sum_c w_c Nc^-1 )^-1 sum_c w_c Nc^-1 x_c(t)
%       s2_c(t)    = v_c' Nc^-1 v_c / r_c(t),  v_c = x_c - x^
%       r_c(t)     = P - tr( H * w_c Nc^-1 ),  H = (sum w Nc^-1)^-1
%
%   The redundancy term is essential: v_c is correlated with x^ and the
%   factors would otherwise be biased low (Python-validated: recovery of
%   known time-varying factors within statistical scatter; combined
%   field beats every single center). Per-center noise SHAPES Nc are the
%   empirical (order, C/S, parity) block covariances of each center's
%   own climatology residuals (shLowLevel.buildNoiseCov), TRACE-NORMALIZED to
%   mean unit variance so that s2_c(t) carries each center's absolute
%   noise power (comparable across centers; the combination weights are
%   invariant under the normalization) - all algebra runs block-wise,
%   O(sum p_b^3) per month.
%
%   Inputs
%     tsCell  1 x C cell of shSeries, equal nmax, >= 2 centers
%   Options
%     Tolerance (0.05)  [yr] epoch matching (centers date mid-months
%                       slightly differently)
%     AllowMissing (true)  months missing at some centers are combined
%                       from the available ones (weights renormalize);
%                       false: only fully-covered months are kept
%     Robust (false)    per-month factor = median over blocks of the
%                       unbiased block estimates q_b/r_b instead of the
%                       global ratio (outlier-month protection;
%                       Python-validated design)
%     MaxIter (6), Tol (1e-3)  VCE iteration control
%   Outputs
%     tsComb  shSeries  combined stacks on the reference epochs (first
%             center), sigmaCs/Ss = posterior sqrt(diag(H)) per month,
%             provenance in history
%     info    struct: s2 (C x T variance factors, NaN where missing),
%             weights (C x T, normalized 1/s2), redundancy (C x T),
%             interCenterCorr (C x C, empirical residual correlation -
%             the honesty diagnostic: VCE assumes independence, GRACE
%             centers share data and background models), nIter, epochs,
%             centers, note
%
%   Combine on GSM level BEFORE TN-14/TN-13 replacements (identical for
%   all centers - apply once afterwards). Common-mode errors (shared
%   K-band data, AOD1B, tides) are invisible to inter-center VCE: the
%   posterior sigmas are a lower bound (documented).
%
%   Claude (Fable 5), 2026-08-07 (v2.4).
%   Developed by Matthias Weigelt with the help of Claude (Fable 5).
arguments
    tsCell (1,:) cell
    opts.Tolerance (1,1) double = 0.05
    opts.AllowMissing (1,1) logical = true
    opts.Robust (1,1) logical = false
    opts.MaxIter (1,1) double {mustBeInteger, mustBePositive} = 6
    opts.Tol (1,1) double = 1e-3
end
C = numel(tsCell);
assert(C >= 2, 'shLowLevel:combineCenters:tooFewCenters', ...
    'Need at least 2 series (got %d).', C);
nmax = tsCell{1}.nmax;
for c = 2:C
    assert(tsCell{c}.nmax == nmax, 'shLowLevel:combineCenters:nmaxMismatch', ...
        'All series must share nmax (center 1: %d, center %d: %d).', ...
        nmax, c, tsCell{c}.nmax);
end
idx = shLowLevel.shIndex(nmax, MinDegree = 0);
n1 = nmax + 1;

% ---- per-center noise shapes from own climatology residuals (static)
Ni = cell(C, 1); rows = []; nb = 0;
for c = 1:C
    ts = tsCell{c};
    X = zeros(idx.P, ts.nEpochs);
    for t = 1:ts.nEpochs
        X(:, t) = shLowLevel.vecFromCS(ts.Cs(:, :, t), ts.Ss(:, :, t), idx);
    end
    if ts.nEpochs > 8
        [~, Xres] = shLowLevel.fitDeterministicModel(X, ts.epochs);
    else
        % too few epochs for the 6-parameter deterministic model: mean
        % removal only (avoids meaningless fits and the fewEpochs
        % warning; noise shapes from < 9 months are crude anyway)
        Xres = X - mean(X, 2);
    end
    Nc = shLowLevel.buildNoiseCov(Xres, idx, Assemble = 'blocks');
    if c == 1
        rows = Nc.blocks; nb = numel(rows);
    end
    % trace-normalize the shape (mean unit variance): the center's
    % ABSOLUTE noise power then lives in s2_c(t), making the factors
    % comparable across centers (weights w_c Nc^-1 are invariant under
    % this rescaling; v2.4.1, exposed by the recovery test).
    tr = 0;
    for b = 1:nb, tr = tr + trace(Nc.mats{b}); end
    scl = idx.P / tr;
    Ni{c} = cell(nb, 1);
    for b = 1:nb
        Ni{c}{b} = inv(Nc.mats{b} * scl);
    end
end

% ---- epoch matching against the reference (center 1)
epochs = tsCell{1}.epochs;
T = numel(epochs);
J = nan(C, T);
J(1, :) = 1:T;
for c = 2:C
    for t = 1:T
        [dt, j] = min(abs(tsCell{c}.epochs - epochs(t)));
        if dt <= opts.Tolerance, J(c, t) = j; end
    end
end
have = ~isnan(J);
if ~opts.AllowMissing
    keep = all(have, 1);
    epochs = epochs(keep); J = J(:, keep); have = have(:, keep);
    T = numel(epochs);
end
assert(T >= 1, 'shLowLevel:combineCenters:noCommonEpochs', ...
    'No epochs matched across centers within %.3f yr.', opts.Tolerance);

% ---- coefficient stacks in idx order
Xc = cell(C, 1);
for c = 1:C
    Xc{c} = nan(idx.P, T);
    for t = 1:T
        if have(c, t)
            j = J(c, t);
            Xc{c}(:, t) = shLowLevel.vecFromCS(tsCell{c}.Cs(:, :, j), ...
                tsCell{c}.Ss(:, :, j), idx);
        end
    end
end

% ---- VCE iteration, block-wise
s2 = ones(C, T); s2(~have) = NaN;
xh = zeros(idx.P, T);
Hd = zeros(idx.P, T);                                % posterior diag
red = nan(C, T);
for it = 1:opts.MaxIter
    s2old = s2;
    for t = 1:T
        cs = find(have(:, t))';
        qAll = zeros(C, 1); rAll = zeros(C, 1);
        qB = nan(C, nb); rB = nan(C, nb);
        for b = 1:nb
            rb = rows{b};
            Sw = zeros(numel(rb));
            for c = cs
                Sw = Sw + Ni{c}{b} / s2(c, t);
            end
            Hb = inv(Sw);
            v = zeros(numel(rb), 1);
            for c = cs
                v = v + (Ni{c}{b} / s2(c, t)) * Xc{c}(rb, t);
            end
            xb = Hb * v;
            xh(rb, t) = xb;
            Hd(rb, t) = diag(Hb);
            for c = cs
                vc = Xc{c}(rb, t) - xb;
                qB(c, b) = vc' * Ni{c}{b} * vc;
                rB(c, b) = numel(rb) - trace(Hb * Ni{c}{b}) / s2(c, t);
            end
        end
        for c = cs
            qAll(c) = sum(qB(c, :));
            rAll(c) = sum(rB(c, :));
            if opts.Robust
                s2(c, t) = median(qB(c, :) ./ max(rB(c, :), 1), 'omitnan');
            else
                s2(c, t) = qAll(c) / max(rAll(c), 1);
            end
            % guard against exact zero ONLY - any absolute floor here
            % is a bug: with trace-normalized shapes the factors live at
            % the DATA variance scale (~1e-20 for Stokes residuals); a
            % 1e-12 floor clamped all centers to the same value and
            % returned exact 1:1:1 ratios (diagnosed via the recovery
            % test + Python reproduction, v2.4.1)
            s2(c, t) = max(s2(c, t), 1e-300);
            red(c, t) = rAll(c);
        end
    end
    dmax = max(abs(s2(:) ./ s2old(:) - 1), [], 'omitnan');
    if dmax < opts.Tol, break; end
end

% ---- inter-center residual correlation (honesty diagnostic)
V = nan(C, idx.P * T);
for c = 1:C
    v = Xc{c} - xh; v(:, ~have(c, :)) = NaN;
    V(c, :) = v(:)';
end
icc = eye(C);
for a = 1:C
    for b2 = a+1:C
        ok = ~isnan(V(a, :)) & ~isnan(V(b2, :));
        if nnz(ok) > 10
            r = corrcoef(V(a, ok)', V(b2, ok)');
            icc(a, b2) = r(1, 2); icc(b2, a) = r(1, 2);
        end
    end
end

% ---- assemble combined series with posterior sigmas
Cs = zeros(n1, n1, T); Ss = zeros(n1, n1, T);
sCs = zeros(n1, n1, T); sSs = zeros(n1, n1, T);
for t = 1:T
    [Cs(:, :, t), Ss(:, :, t)] = shLowLevel.csFromVec(xh(:, t), idx);
    [sCs(:, :, t), sSs(:, :, t)] = shLowLevel.csFromVec(sqrt(max(Hd(:, t), 0)), idx);
end
names = strings(1, C);
for c = 1:C, names(c) = tsCell{c}.productType; end
tsComb = shSeries(Cs, Ss = Ss, Epochs = epochs, ProductType = "GSM", ...
    SigmaCs = sCs, SigmaSs = sSs, History = sprintf( ...
    "combined from %d centers, per-(center,month) VCE (robust=%d, %d iters)", ...
    C, opts.Robust, it));
w = 1 ./ s2; w = w ./ sum(w, 1, 'omitnan');
info = struct('s2', s2, 'weights', w, 'redundancy', red, ...
    'interCenterCorr', icc, 'nIter', it, 'epochs', epochs, ...
    'centers', names, 'note', ...
    ['common-mode errors (shared K-band, AOD1B, tides) are invisible ' ...
     'to inter-center VCE: posterior sigmas are a lower bound']);
end
