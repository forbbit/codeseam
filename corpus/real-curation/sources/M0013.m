function [ts, rep] = gravisL2B(folder, gravisFolder, opts)
%GRAVISL2B Build a GravIS-Level-2B-equivalent series from monthly fields.
%
%   [TS, REP] = shLowLevel.gravisL2B(FOLDER, GRAVISFOLDER) reproduces the
%   GravIS Level-2B correction chain (Dahle & Murboeck 2025) on a folder
%   of monthly .gfc solutions, exactly as validated against the GravIS
%   Greenland, Antarctica and TWS Level-3 products (guide chapters
%   V1-V8):
%     1. read all monthly solutions (shSeries.fromFolder)
%     2. replace C20, C30, C21, S21 from the GravIS GRACE+SLR
%        low-degree table, matched on the BEGIN epoch parsed from the
%        GSM-2_YYYYDDD-YYYYDDD filenames
%     3. insert degree 1 (C10, C11, S11) from the GravIS geocenter table
%     4. subtract the GravIS NFIL mean field (anomalies w.r.t.
%        2002-04..2020-03 by default)
%     5. optionally subtract a GIA rate field as (t - GIAEpoch) * GIA
%   Epochs the correction tables do not reach are DROPPED and recorded
%   (the tables always trail the solutions); OnMissing="error" restores
%   a hard stop. This is the shared core of greenlandChain,
%   antarcticaChain and twsChain.
%
%   Inputs
%     folder        (1,1) string  folder of monthly GSM-2_*.gfc(.gz)
%     gravisFolder  (1,1) string  folder holding the GravIS aux files.
%                   "" (default) uses the frozen copies shipped in
%                   data/gravis (see shLowLevel.gravisDataFolder). The
%                   tables trail the solutions: for epochs after the
%                   freeze fetch fresh files from https://isdc-data.
%                   gfz.de/grace/GravIS/COST-G/Level-2B/aux_data/
%
%   Options
%     LowDegreeFile ("GRAVIS-2B_COSTG_0200_GRACE+SLR_LOW_DEGREES_0001.dat")
%     GeocenterFile ("GRAVIS-2B_COSTG_0200_GEOCENTER_0001.dat")
%     MeanFile      ("GRAVIS-2B_COSTG_0200_MEAN_2002095-2020091_NFIL_0001.gz")
%     GIAFile       ("")     SHM rate file; "" skips step 5. The GravIS
%                    product is GRAVIS-2B_COSTG_0200_GIA_ICE-6G_D_VM5a_0001.gz
%     GIAEpoch      (2011)   reference epoch of the GIA rate (GravIS
%                    centres ICE-6G_D on 2011)
%     Nmax          (90)     truncation degree
%     Pattern       ("GSM-2_*.gfc*")  file pattern
%     Tolerance     (2e-3)   max |begin difference| [yr] for a table match
%     OnMissing     ("drop") "drop" | "error" for uncovered epochs
%     SpanEnd       (Inf)    keep epochs <= SpanEnd only (decimal years);
%                    the published ice trends pin 2023.099 (guide V3)
%     Quiet         (false)
%
%   Outputs
%     ts   (1,1) shSeries  corrected anomaly series (nmax = Nmax)
%     rep  (1,1) struct    steps (1,K string), epochs (T,1), nDropped,
%          begins (T,1), files, nmax, version, created
%
%   Example
%     [ts, rep] = shLowLevel.gravisL2B("E:/series/COSTG", ...   % shipped aux data
%         GIAFile = "GRAVIS-2B_COSTG_0200_GIA_ICE-6G_D_VM5a_0001.gz");
%
%   Developed by Matthias Weigelt with the help of Claude (Fable 5),
%   2026-08-12 (v3.8.8).
arguments
    folder (1,1) string
    gravisFolder (1,1) string = ""
    opts.LowDegreeFile (1,1) string = "GRAVIS-2B_COSTG_0200_GRACE+SLR_LOW_DEGREES_0001.dat"
    opts.GeocenterFile (1,1) string = "GRAVIS-2B_COSTG_0200_GEOCENTER_0001.dat"
    opts.MeanFile (1,1) string = "GRAVIS-2B_COSTG_0200_MEAN_2002095-2020091_NFIL_0001.gz"
    opts.GIAFile (1,1) string = ""
    opts.GIAEpoch (1,1) double = 2011
    opts.Nmax (1,1) double {mustBeInteger, mustBePositive} = 90
    opts.Pattern (1,1) string = "GSM-2_*.gfc*"
    opts.Tolerance (1,1) double {mustBePositive} = 2e-3
    opts.OnMissing (1,1) string {mustBeMember(opts.OnMissing, ["drop","error"])} = "drop"
    opts.SpanEnd (1,1) double = Inf
    opts.Quiet (1,1) logical = false
end
if strlength(gravisFolder) == 0
    gravisFolder = shLowLevel.gravisDataFolder();
end
steps = strings(1, 0);
resolve = @(f) local_resolve(gravisFolder, f);
% ---- 1. read + span
ts = shSeries.fromFolder(folder, Pattern = opts.Pattern);
ep = ts.epochs(:);
if isfinite(opts.SpanEnd)
    ts = ts.select(ep <= opts.SpanEnd + 0.05);
    ep = ts.epochs(:);
end
T = ts.nEpochs;
steps(end+1) = sprintf("read %d epochs (nmax %d)", T, ts.nmax);
% ---- begins from the filenames (fromFolder epochs are mid-months)
d = dir(fullfile(char(folder), char(opts.Pattern)));
[~, si] = sort({d.name}); d = d(si);
tok = regexp({d.name}, 'GSM-2_(\d{4})(\d{3})-(\d{4})(\d{3})', 'tokens', 'once');
ok = ~cellfun(@isempty, tok);
d = d(ok); tok = tok(ok);
yd = @(y) 365 + double(mod(y,4)==0 & (mod(y,100)~=0 | mod(y,400)==0));
nf = numel(tok); begF = zeros(nf,1); midF = zeros(nf,1);
for k = 1:nf
    y1 = str2double(tok{k}{1}); d1 = str2double(tok{k}{2});
    y2 = str2double(tok{k}{3}); d2 = str2double(tok{k}{4});
    begF(k) = y1 + (d1-1)/yd(y1);
    midF(k) = (begF(k) + y2 + d2/yd(y2)) / 2;
end
[midF, si2] = sort(midF); begF = begF(si2);
keepSpan = true(nf, 1);
if isfinite(opts.SpanEnd), keepSpan = midF <= opts.SpanEnd + 0.05; end
begF = begF(keepSpan); midF = midF(keepSpan);
if numel(midF) ~= T || max(abs(midF - ep)) >= 5e-3
    error('shLowLevel:gravisL2B:epochMismatch', ...
        ['The GSM-2 filename epochs do not line up with the series ' ...
         'epochs (%d files vs %d epochs) - mixed products in FOLDER?'], ...
        numel(midF), T);
end
% ---- 2+3. aux corrections, matched on begin
LD = local_table(resolve(opts.LowDegreeFile), 12);
GC = local_table(resolve(opts.GeocenterFile), 9);
Cs = ts.Cs; Ss = ts.Ss;
covered = true(T, 1); iL = zeros(T,1); iG = zeros(T,1);
for k = 1:T
    [dL, iL(k)] = min(abs(LD(:,2) - begF(k)));
    [dG, iG(k)] = min(abs(GC(:,2) - begF(k)));
    covered(k) = dL < opts.Tolerance && dG < opts.Tolerance;
end
if any(~covered)
    if opts.OnMissing == "error"
        error('shLowLevel:gravisL2B:uncovered', ...
            '%d epochs are not covered by the correction tables.', nnz(~covered));
    end
    steps(end+1) = sprintf("dropped %d uncovered epochs", nnz(~covered));
end
for k = find(covered)'
    Cs(3,1,k) = LD(iL(k),3);  Cs(4,1,k) = LD(iL(k),6);
    Cs(3,2,k) = LD(iL(k),9);  Ss(3,2,k) = LD(iL(k),12);
    Cs(2,1,k) = GC(iG(k),3);  Cs(2,2,k) = GC(iG(k),6);  Ss(2,2,k) = GC(iG(k),9);
end
Cs = Cs(:,:,covered); Ss = Ss(:,:,covered);
ep = ep(covered); begF = begF(covered); T = numel(ep);
steps(end+1) = "replaced C20/C30/C21/S21 (GravIS GRACE+SLR) and degree 1 (GravIS geocenter)";
% ---- 4. mean
nmax = min(size(Cs,1)-1, opts.Nmax);
Mn = shLowLevel.readSHM(resolve(opts.MeanFile), Nmax = nmax);
Cs = Cs(1:nmax+1, 1:nmax+1, :); Ss = Ss(1:nmax+1, 1:nmax+1, :);
for k = 1:T
    Cs(:,:,k) = Cs(:,:,k) - Mn.C(1:nmax+1, 1:nmax+1);
    Ss(:,:,k) = Ss(:,:,k) - Mn.S(1:nmax+1, 1:nmax+1);
end
steps(end+1) = "subtracted the NFIL mean field";
% ---- 5. GIA
if strlength(opts.GIAFile) > 0
    Gi = shLowLevel.readSHM(resolve(opts.GIAFile), Nmax = nmax);
    for k = 1:T
        Cs(:,:,k) = Cs(:,:,k) - (ep(k) - opts.GIAEpoch) * Gi.C(1:nmax+1, 1:nmax+1);
        Ss(:,:,k) = Ss(:,:,k) - (ep(k) - opts.GIAEpoch) * Gi.S(1:nmax+1, 1:nmax+1);
    end
    steps(end+1) = sprintf("subtracted GIA rate (%s, epoch %.1f)", ...
        opts.GIAFile, opts.GIAEpoch);
end
ts = shSeries(Cs, Ss = Ss, Epochs = ep);
if ~opts.Quiet, fprintf('  %s\n', steps); end
rep = struct('steps', steps, 'epochs', ep, 'nDropped', nnz(~covered), ...
    'begins', begF, 'nmax', nmax, 'version', shLowLevel.version(), ...
    'created', string(datetime('now')));
end

function fp = local_resolve(base, f)
fp = char(f);
if ~isfile(fp), fp = fullfile(char(base), char(f)); end
if ~isfile(fp)
    error('shLowLevel:gravisL2B:missingAux', ...
        ['GravIS aux file not found: %s (looked in %s). Fetch it from ' ...
         'https://isdc-data.gfz.de/grace/GravIS/COST-G/Level-2B/aux_data/'], ...
        f, base);
end
end

function M = local_table(fp, ncol)
M = readmatrix(fp, FileType = 'text', CommentStyle = '#');
if size(M, 2) < ncol
    error('shLowLevel:gravisL2B:badTable', ...
        '%s has %d columns, expected >= %d.', fp, size(M,2), ncol);
end
end
