function [rep, h] = compareSeries(tsList, opts)
%COMPARESERIES Temporal + component comparison of N solution series.
%
%   REP = shLowLevel.compareSeries({TS1, TS2, ...}) compares N >= 2 shSeries
%   against the FIRST (the reference) on a COMMON BASIS: epochs are
%   matched to the reference within MatchTolerance (0.02) (unmatched epochs
%   are dropped and reported - never interpolated across gaps), all
%   series are truncated to the smallest nmax, and GM/R are unified.
%   Per solution k >= 2 the standard temporal metric set is computed on
%   a scalar comparison series y_k(t) - a basin average when Basin ([])= is
%   given (recommended for hydrology; below the filter resolution,
%   pointwise differences are leakage artefacts), otherwise the
%   area-weighted mean of the synthesized quantity over Mask ([]):
%     - Nash-Sutcliffe efficiency (skill; punishes bias and amplitude)
%     - correlation with AR(1)-corrected significance (shLowLevel.effectiveCorr)
%     - trend difference +- combined sigma and significance z (Kendall
%       AR(1)-corrected fits per series)
%     - annual amplitude ratio and phase lag [days]
%     - chi^2/dof of coefficient differences vs combined formal sigmas
%       (error realism; NaN when sigmas are absent)
%   Component fields: each solution's climatology trend minus the
%   reference trend as shCoefficients (sigmas RSS'd), with its degree
%   spectrum. With N >= 3, the generalized three-cornered hat assigns
%   an individual noise level to every solution - the question pairwise
%   metrics cannot answer.
%   [REP, H] = shLowLevel.compareSeries(..., Plot (false) = true) adds a 4-panel
%   figure: comparison series, Taylor diagram vs the reference,
%   trend-difference spectra, and |y_k - y_ref| over time.
%
%
%   Inputs
%     tsList  (1,N) cell of shSeries  the series to compare; the FIRST is the reference
%   Options
%     Names (strings(1, 0)) ([])            string array, one per series
%     MatchTolerance (0.02) epoch matching tolerance [yr]
%     Basin ([]), Idx ([])  P x 1 basin vector + shLowLevel.shIndex struct:
%                           y = Basin' * coefficient vector per epoch
%     LatDeg (-88:4:88), LonDeg (0:6:354), Quantity ("geoid"), kn ([]),
%     Mask ([])             synthesis path when Basin is not given
%     Plot (false)
%
%   Outputs
%     rep        (1,1) struct  fields:
%                  .names      (1,N) string
%                  .epochs     (T,1) double  common epochs used
%                  .nDropped   (1,N) double  reference epochs unmatched per series
%                  .y          (T,N) double  comparison series (col 1 = reference)
%                  .nse        (1,N) double  NSE vs reference (NaN for col 1)
%                  .corr       (1,N) struct-array-free: Pearson r per series
%                  .pcorr      (1,N) double  AR(1)-corrected two-sided p
%                  .neff       (1,N) double  effective sample sizes
%                  .trendDiff  (1,N) double  trend - reference trend [units/yr]
%                  .trendSigma (1,N) double  combined 1-sigma of trendDiff
%                  .trendZ     (1,N) double  significance z of trendDiff
%                  .ampRatio   (1,N) double  annual amplitude / reference
%                  .phaseLagDays (1,N) double annual phase lag vs reference
%                  .chi2dof    (1,N) double  error realism vs reference
%                  .trendDiffFields (1,N) cell shCoefficients (empty for col 1)
%                  .tch        (1,1) struct  shLowLevel.threeCorneredHat output (N >= 3)
%                  .nmax       (1,1) double  common maximum degree
%     h          (1,1) graphics handle  figure handle (Plot = true only)
%
%   Example
%     rep = shLowLevel.compareSeries({tsCSR, tsGFZ, tsJPL}, ...
%         Names = ["CSR", "GFZ", "JPL"]);
%     fprintf("TCH noise: %s\n", sprintf("%.3g ", rep.tch.sigma))
%
%   Developed by Matthias Weigelt with the help of Claude (Fable 5),
%   2026-08-08 (v2.6.0).
arguments
    tsList (1,:) cell
    opts.Names string = strings(1, 0)
    opts.MatchTolerance (1,1) double = 0.02
    opts.Basin double = []
    opts.Idx = []
    opts.LatDeg (1,:) double = -88:4:88
    opts.LonDeg (1,:) double = 0:6:354
    opts.Quantity (1,1) string = "geoid"
    opts.kn double = []
    opts.Mask = []
    opts.Plot (1,1) logical = false
end
N = numel(tsList);
if N < 2
    error('shLowLevel:compareSeries:needTwo', 'Need at least 2 series.');
end
for k = 1:N
    if ~isa(tsList{k}, 'shSeries')
        error('shLowLevel:compareSeries:badInput', ...
            'Entry %d is not an shSeries.', k);
    end
end
names = opts.Names;
if numel(names) ~= N
    names = "solution " + string(1:N);
end
% ---- common epochs: match every series to the reference
tRef = tsList{1}.epochs(:);
sel = false(numel(tRef), N); pick = zeros(numel(tRef), N);
for k = 1:N
    tk = tsList{k}.epochs(:);
    for i = 1:numel(tRef)
        [dmin, j] = min(abs(tk - tRef(i)));
        if dmin <= opts.MatchTolerance
            sel(i, k) = true; pick(i, k) = j;
        end
    end
end
common = all(sel, 2);
nDropped = sum(~sel, 1);                        % per series vs full ref
if nnz(common) < 12
    error('shLowLevel:compareSeries:tooFewEpochs', ...
        'Only %d common epochs (need >= 12).', nnz(common));
end
tC = tRef(common);
T = numel(tC);
% ---- common nmax + GM/R, subset every series
nmax = min(cellfun(@(t) t.nmax, tsList));
for k = 1:N
    tk = tsList{k};
    keepIdx = pick(common, k);
    lg = false(tk.nEpochs, 1); lg(keepIdx) = true;
    tk = tk.select(lg);
    if tk.nmax > nmax, tk = tk.truncate(nmax); end
    tsList{k} = tk;
end
% ---- comparison series y (T x N)
useBasin = ~isempty(opts.Basin);
if useBasin && isempty(opts.Idx)
    error('shLowLevel:compareSeries:basinNeedsIdx', ...
        'Basin= requires the matching Idx= (shLowLevel.shIndex struct).');
end
y = nan(T, N);
if useBasin
    b = opts.Basin(:);
    for k = 1:N
        tk = tsList{k};
        for t = 1:T
            g = tk.at(t);
            y(t, k) = b' * shLowLevel.vecFromCS(g.C, g.S, opts.Idx);
        end
    end
else
    w = cosd(opts.LatDeg(:)) * ones(1, numel(opts.LonDeg));
    if ~isempty(opts.Mask), w(~logical(opts.Mask)) = 0; end
    w = w / sum(w(:));
    for k = 1:N
        tk = tsList{k};
        for t = 1:T
            g = tk.at(t);
            G = g.synthesis(opts.LatDeg, opts.LonDeg, ...
                quantity = opts.Quantity, kn = opts.kn);
            y(t, k) = sum(w(:) .* G(:));
        end
    end
end
% ---- temporal metrics vs the reference
nse = nan(1, N); r = nan(1, N); pcorr = nan(1, N); neff = nan(1, N);
trendDiff = nan(1, N); trendSigma = nan(1, N); trendZ = nan(1, N);
ampRatio = nan(1, N); phaseLagDays = nan(1, N); chi2 = nan(1, N);
tr = zeros(1, N); trS = zeros(1, N); amp = zeros(1, N); ph = zeros(1, N);
for k = 1:N
    [~, ~, coef, ~, coefSigma] = shLowLevel.fitDeterministicModel( ...
        y(:, k)', tC, ARCorrect = true);
    c = coef(:); cs = coefSigma(:);
    tr(k) = c(2); trS(k) = cs(2);
    amp(k) = hypot(c(3), c(4));
    ph(k) = atan2(c(4), c(3)) / (2 * pi);       % annual phase [yr]
end
for k = 2:N
    nse(k) = shLowLevel.nashSutcliffe(y(:, 1), y(:, k));
    ec = shLowLevel.effectiveCorr(y(:, 1), y(:, k));
    r(k) = ec.r; pcorr(k) = ec.p; neff(k) = ec.neff;
    trendDiff(k) = tr(k) - tr(1);
    trendSigma(k) = hypot(trS(k), trS(1));
    trendZ(k) = trendDiff(k) / trendSigma(k);
    ampRatio(k) = amp(k) / amp(1);
    dph = ph(k) - ph(1);
    dph = dph - round(dph);                     % wrap to +-0.5 yr
    phaseLagDays(k) = 365.25 * dph;
end
% ---- error realism: coefficient-domain chi2 vs combined sigmas
idx = shLowLevel.shIndex(nmax);
hasSig = cellfun(@(t) ~isempty(t.sigmaCs), tsList);
if hasSig(1)
    for k = 2:N
        if ~hasSig(k), continue, end
        acc = 0; nn = 0;
        for t = 1:T
            gr = tsList{1}.at(t); gk = tsList{k}.at(t);
            d = shLowLevel.vecFromCS(gr.C - gk.C, gr.S - gk.S, idx);
            s2 = shLowLevel.vecFromCS(gr.sigmaC, gr.sigmaS, idx).^2 + ...
                 shLowLevel.vecFromCS(gk.sigmaC, gk.sigmaS, idx).^2;
            use = isfinite(d) & isfinite(s2) & s2 > 0;
            acc = acc + sum(d(use).^2 ./ s2(use)); nn = nn + nnz(use);
        end
        if nn > 0, chi2(k) = acc / nn; end
    end
end
% ---- component fields: trend difference vs reference
climRef = tsList{1}.climatology();
gTrRef = climRef.trend();
trendDiffFields = cell(1, N);
for k = 2:N
    climK = tsList{k}.climatology();
    trendDiffFields{k} = climK.trend() - gTrRef;   % sigmas RSS'd by minus
end
% ---- three-cornered hat (N >= 3)
tch = struct('sigma', nan(1, N));
if N >= 3
    tch = shLowLevel.threeCorneredHat(y);
end
rep = struct('names', names, 'epochs', tC, 'nDropped', nDropped, ...
    'y', y, 'nse', nse, 'corr', r, 'pcorr', pcorr, 'neff', neff, ...
    'trendDiff', trendDiff, 'trendSigma', trendSigma, 'trendZ', trendZ, ...
    'ampRatio', ampRatio, 'phaseLagDays', phaseLagDays, 'chi2dof', chi2, ...
    'trendDiffFields', {trendDiffFields}, 'tch', tch, 'nmax', nmax);
% ---- visualization
h = gobjects(0);
if opts.Plot
    h = figure('Color', 'w');
    tiledlayout(h, 2, 2, 'Padding', 'compact');
    cols = lines(N);
    nexttile; hold on;
    for k = 1:N
        plot(tC, y(:, k), '.-', 'Color', cols(k, :));
    end
    hold off; grid on; xlabel('epoch [yr]'); legend(names, 'Location', 'best');
    title('comparison series');
    nexttile;
    y0 = y(:, 1) - mean(y(:, 1));
    stds = zeros(1, N - 1); cors = zeros(1, N - 1);
    for k = 2:N
        yk = y(:, k) - mean(y(:, k));
        stds(k-1) = std(yk);
        cors(k-1) = (y0' * yk) / (norm(y0) * norm(yk));
    end
    shLowLevel.taylorDiagram(std(y0), stds, cors, Labels = names(2:end), ...
        Title = "temporal Taylor vs " + names(1));
    nexttile; hold on;
    for k = 2:N
        gd = trendDiffFields{k};
        sp = shLowLevel.shDegreeRMS(gd.C, gd.S);
        semilogy(sp.degree, sp.degAmplitude, '.-', 'Color', cols(k, :));
    end
    hold off; grid on; set(gca, 'YScale', 'log');
    xlabel('degree n'); ylabel('trend diff amplitude');
    legend(names(2:end), 'Location', 'best'); title('trend difference spectra');
    nexttile; hold on;
    for k = 2:N
        plot(tC, abs(y(:, k) - y(:, 1)), '.-', 'Color', cols(k, :));
    end
    hold off; grid on; xlabel('epoch [yr]'); ylabel('|y_k - y_{ref}|');
    title('difference series');
end
end
