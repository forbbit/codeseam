function [out, rep] = oceanChain(folder, opts)
%OCEANCHAIN Global-ocean mass chain: barystatic series from GSM + GravIS.
%
%   [OUT, REP] = shLowLevel.oceanChain(FOLDER, kn = KN, OceanMask = OC)
%   runs the ocean sibling of the validated chains (roadmap item 7):
%   gravisL2B corrections (C20/C30/C21/S21, degree 1, minus NFIL mean,
%   GIA rate ON by default - the ocean-floor GIA correction matters for
%   barystatic trends) -> global EWH synthesis on a GridStep graticule
%   -> area-weighted ocean-mean series [cm] -> trend + annual fit. The
%   residual after the per-pixel trend+seasonal fit is what remains for
%   the noise proxy: this chain SEPARATES the real open-ocean signal
%   (barystatic rise + seasonal circulation) from the residual that
%   oceanRMS should see - the guide-V6 finding ("the trend's open-ocean
%   RMS is mostly real barystatic signal, not error") as an API.
%
%   Full restoration (Chambers & Willis 2010) is opt-in: GADFolder=
%   adds the model ocean signal back on the coefficient level and
%   GAAFolder= subtracts the ocean mean of the atmospheric product per
%   epoch; shLowLevel.fetchGAX downloads both from 2002 on. Without
%   them the TREND stays interpretable (AOD1B carries no secular trend
%   by construction) while sub-annual ocean variability is incomplete.
%
%   Filter note: GAD is added BEFORE the filter, so model and
%   observation see the same smoothing (the GravIS Level-3 order). The
%   ocean MEAN is filter-invariant to 0.01 mm/yr (measured); pixel
%   FIELDS are not - declare the filter when comparing gridded output
%   (see shLowLevel.obpChain for the field product).
%
%   Inputs
%     folder  (1 x 1) string  monthly .gfc folder (GSM-2_*, any centre)
%
%   Options
%     kn ([])            (N x 2 | N x 1) REQUIRED load Love numbers
%     OceanMask ([])     (fn handle | nLat x nLon logical) REQUIRED ocean
%                        decision @(lat, lon) -> logical, MUST be false
%                        over land (oceanRMS contract; the chains'
%                        documented 5 Gt/yr latitude-band lesson)
%     gravisFolder ("")  GravIS aux folder; "" = shipped data/gravis
%     GIAFile ("GRAVIS-2B_COSTG_0200_GIA_ICE-6G_D_VM5a_0001.gz")
%                        "" disables the GIA rate; the default
%                        ocean-floor correction raises the barystatic
%                        trend by about +1 mm/yr (the guide-V10 lever)
%     GIAEpoch (2011)    (1 x 1) GIA reference epoch
%     Filter ("gauss445") "none" | "gaussN" [km]; the ocean MEAN is
%                        nearly filter-invariant, but sigMon describes
%                        the filtered world - unfiltered, the pixel
%                        residuals are stripe-dominated (1.6 m measured)
%     GridStep (1)       (1 x 1) synthesis graticule [deg]
%     SpanEnd ([])       (1 x 1) keep epochs <= SpanEnd [decimal years]
%     GADFolder ("")     folder of GAD-2_*.gfc; when set, epochs with a
%                        begin-matched GAD file get it added back on the
%                        coefficient level and REP records covered and
%                        uncovered epochs (fetch via shLowLevel.fetchGAX)
%     GAAFolder ("")     folder of GAA-2_*.gfc; when set, the ocean MEAN
%                        of GAA is subtracted per epoch (Chambers &
%                        Willis 2010) - removes the atmospheric
%                        land-ocean mass term that GRACE sees but that
%                        is not water
%     SeparateCirculation (false) split the pixel residuals (after the
%                        trend + seasonal fit) into coherent residual
%                        circulation and noise via shLowLevel.eofSeparate
%                        (North rule); sigMon is then the NOISE RMS and
%                        OUT gains circulationRMS / nModes / lamModes
%     Quiet (true)       (1 x 1) suppress progress output
%
%   Outputs
%     out  (1 x 1) struct with fields
%       epochs    (T x 1) decimal years
%       oceanMean (T x 1) area-weighted ocean-mean EWH [cm]
%       trend     (1 x 1) barystatic trend [mm/yr]
%       trendGt   (1 x 1) the same as mass rate [Gt/yr] over the mask
%       trendSigma (1 x 1) OLS 1-sigma of the trend [mm/yr] (no AR
%                 correction - stated, not hidden)
%       ampAnnual (1 x 1) annual amplitude of the ocean mean [mm]
%       sigMon    (1 x 1) open-ocean residual RMS after the per-pixel
%                 trend+seasonal fit [m] (the honest noise proxy)
%       oceanArea (1 x 1) mask area [m^2]
%       circulationRMS (1 x 1) area-weighted RMS of the separated
%                 residual circulation [m] (NaN unless
%                 SeparateCirculation)
%       nModes    (1 x 1) EOF modes the North rule kept (0 unless
%                 SeparateCirculation)
%       lamModes  (K x 1) variance per EOF mode ([] unless
%                 SeparateCirculation)
%     rep  (1 x 1) struct  steps, version, dropped/uncovered epochs
%
%   Example
%     kn = readmatrix("loadLoveNumbers_Gegout97.txt", FileType = "text", ...
%         NumHeaderLines = 2);
%     oc = @(la, lo) abs(la) <= 66 & ~yourLandFcn(la, lo);
%     [out, rep] = shLowLevel.oceanChain("E:/series/COSTG", kn = kn, ...
%         OceanMask = oc);
%     plot(out.epochs, out.oceanMean)   % barystatic curve [cm]
%
%   Error identifiers
%     shLowLevel:oceanChain:missingKn  kn not supplied
%
%   Developed by Matthias Weigelt with the help of Claude (Fable 5),
%   2026-08-12 (v3.9.0).
arguments
    folder (1,1) string
    opts.kn double = []
    opts.OceanMask = []
    opts.gravisFolder (1,1) string = ""
    opts.GIAFile (1,1) string = "GRAVIS-2B_COSTG_0200_GIA_ICE-6G_D_VM5a_0001.gz"
    opts.GIAEpoch (1,1) double = 2011
    opts.Filter (1,1) string = "gauss445"
    opts.GridStep (1,1) double {mustBePositive} = 1
    opts.SpanEnd double {mustBeScalarOrEmpty} = []
    opts.GADFolder (1,1) string = ""
    opts.GAAFolder (1,1) string = ""
    opts.SeparateCirculation (1,1) logical = false
    opts.Quiet (1,1) logical = true
end
if isempty(opts.kn)
    error('shLowLevel:oceanChain:missingKn', ...
        'oceanChain requires load Love numbers: pass kn = ... explicitly.');
end
R = 6378136.3; GM = 3.986004415e14; Re = 6371e3;
% ---- corrected series (shared core)
l2bArgs = {'GIAEpoch', opts.GIAEpoch, 'GIAFile', opts.GIAFile};
if ~isempty(opts.SpanEnd), l2bArgs = [l2bArgs, {'SpanEnd', opts.SpanEnd}]; end
[ts, repL] = shLowLevel.gravisL2B(folder, opts.gravisFolder, l2bArgs{:});
ep = ts.epochs(:); T = numel(ep);
steps = repL.steps;
nGad = 0;

% ---- global synthesis + masks
st = opts.GridStep;
lat = (-90+st/2 : st : 90-st/2)'; lon = (st/2 : st : 360-st/2)';
if isa(opts.OceanMask, 'function_handle')
    [LO, LA] = meshgrid(lon, lat);
    mk = logical(opts.OceanMask(LA, LO));
else
    mk = logical(opts.OceanMask);
end
kn = opts.kn; if size(kn, 2) > 1, kn = kn(:, 2); end
Cs = ts.Cs; Ss = ts.Ss;                     % value class: local working copy
nmaxS = size(Cs, 1) - 1;
if strlength(opts.GADFolder) > 0            % optional GAD restore
    [Cs, Ss, nGad] = addGADFolder(Cs, Ss, ep, opts.GADFolder);
    steps(end+1) = sprintf("GAD restored for %d/%d epochs (folder %s)", ...
        nGad, T, opts.GADFolder);
end
if opts.Filter ~= "none"
    rkm = double(extractAfter(opts.Filter, "gauss"));
    wf = shLowLevel.shGaussianWeights(nmaxS, rkm); wf = wf(:);
    for k = 1:T
        Cs(:,:,k) = Cs(:,:,k) .* wf;
        Ss(:,:,k) = Ss(:,:,k) .* wf;
    end
    steps(end+1) = "filter " + opts.Filter + " applied before synthesis";
end
E = zeros(numel(lat), numel(lon), T); Pl = [];
for k = 1:T
    if isempty(Pl)
        [E(:,:,k), ~, ~, Pl] = shLowLevel.shSynthesis(Cs(:,:,k), ...
            Ss(:,:,k), GM, R, lat, lon, 'quantity','ewh', 'kn',kn, 'nmin',0);
    else
        E(:,:,k) = shLowLevel.shSynthesis(Cs(:,:,k), Ss(:,:,k), ...
            GM, R, lat, lon, 'quantity','ewh', 'kn',kn, 'nmin',0, 'P',Pl);
    end
end
steps(end+1) = sprintf("EWH synthesis %d epochs, %g-deg grid, nmax %d", ...
    T, st, nmaxS);
% ---- ocean-mean series + fits
dphi = deg2rad(st); dlam = deg2rad(st);
[~, LA2] = meshgrid(lon, lat);
Apix = (Re^2) * cosd(LA2) * dphi * dlam;
wA = Apix(mk); oceanArea = sum(wA);
X = reshape(E, [], T);
om = (wA' * X(mk(:), :))' / oceanArea * 100;              % cm
A6 = [ones(T,1), ep-mean(ep), cos(2*pi*ep), sin(2*pi*ep), ...
      cos(4*pi*ep), sin(4*pi*ep)];
nGaa = 0;
if strlength(opts.GAAFolder) > 0
    [gaaM, nGaa] = local_gaaOceanMean(opts.GAAFolder, ep, GM, R, lat, lon, ...
        kn, mk, wA, oceanArea);
    om = om - gaaM;                       % Chambers & Willis 2010
    steps(end+1) = sprintf("subtracted GAA ocean mean for %d/%d epochs", ...
        nGaa, T);
end
x = A6 \ om;
r = om - A6*x;
sig = sqrt(sum(r.^2) / (T - 6));
Sxx = sum((ep-mean(ep)).^2);
trend = x(2) * 10;                                        % cm/yr -> mm/yr
trendSigma = sig / sqrt(Sxx) * 10;
ampAnnual = hypot(x(3), x(4)) * 10;                       % mm
trendGt = (x(2)/100) * oceanArea * 1000 / 1e12;           % m/yr*m^2*rho/1e12
% ---- per-pixel residual RMS (the honest noise proxy after separation)
coef = A6 \ X(mk(:), :)';
residRMS = sqrt(mean((X(mk(:), :)' - A6*coef).^2, 1));
sigMon = sqrt(median(residRMS.^2));                       % robust vs coasts
if opts.SeparateCirculation
    Rpx = X(mk(:), :)' - A6 * coef;                       % T x Q residuals
    [circ, nz, infE] = shLowLevel.eofSeparate(Rpx', wA);
    sigMon = infE.rmsNoise;                               % noise, de-circulated
    circulationRMS = sqrt(sum(wA .* mean(circ.^2, 2)) / sum(wA));
    steps(end+1) = sprintf(...
        "EOF separation: %d modes (North), circ RMS %.4f m, noise %.4f m", ...
        infE.nKeep, circulationRMS, sigMon);
else
    circulationRMS = NaN; infE = struct('nKeep', 0, 'lam', []); nz = []; %#ok<NASGU>
end
steps(end+1) = sprintf(...
    "ocean mean: trend %+.2f mm/yr (%+.1f Gt/yr), amp %.1f mm, sigMon %.4f m", ...
    trend, trendGt, ampAnnual, sigMon);
out = struct('epochs', ep, 'oceanMean', om, 'trend', trend, ...
    'trendGt', trendGt, 'trendSigma', trendSigma, 'ampAnnual', ampAnnual, ...
    'sigMon', sigMon, 'oceanArea', oceanArea, ...
    'circulationRMS', circulationRMS, 'nModes', infE.nKeep, ...
    'lamModes', infE.lam);
rep = struct('steps', steps(:), 'version', shLowLevel.version(), ...
    'nEpochs', T, 'nGadRestored', nGad, 'nGaaApplied', nGaa);
if ~opts.Quiet, fprintf('%s\n', steps); end
end


function [gaaM, nGaa] = local_gaaOceanMean(gaaFolder, ep, GM, R, lat, lon, ...
    kn, mk, wA, oceanArea)
% per-epoch ocean mean of GAA [cm], begin-matched like GAD; epochs
% without a file keep 0 (recorded by the caller)
df = dir(fullfile(char(gaaFolder), 'GAA-2_*.gfc'));
tok = regexp({df.name}, 'GAA-2_(\d{4})(\d{3})-', 'tokens', 'once');
yd = @(y) 365 + double(mod(y,4)==0 & (mod(y,100)~=0 | mod(y,400)==0));
begG = nan(numel(tok), 1);
for k = 1:numel(tok)
    y = str2double(tok{k}{1}); d = str2double(tok{k}{2});
    begG(k) = y + (d-1)/yd(y);
end
T = numel(ep); gaaM = zeros(T, 1); nGaa = 0; Pl = [];
for k = 1:T
    [dmin, j] = min(abs(begG - (ep(k) - 15/365)));
    if isempty(dmin) || dmin > 0.05, continue; end
    g = shCoefficients.read(fullfile(df(j).folder, df(j).name));
    if isempty(Pl)
        [E, ~, ~, Pl] = shLowLevel.shSynthesis(g.C, g.S, GM, R, lat, lon, ...
            'quantity', 'ewh', 'kn', kn(1:size(g.C,1)), 'nmin', 0);
    else
        E = shLowLevel.shSynthesis(g.C, g.S, GM, R, lat, lon, ...
            'quantity', 'ewh', 'kn', kn(1:size(g.C,1)), 'nmin', 0, 'P', Pl);
    end
    gaaM(k) = (wA' * E(mk)) / oceanArea * 100;
    nGaa = nGaa + 1;
end
end