function out = readSHM(filename, opts)
%READSHM Read a GRAVIS/GRACE SHM file (GRCOF2 fields, GRDOTA rates).
%
%   OUT = shLowLevel.readSHM(FILENAME) reads the spherical-harmonic
%   format used by the GRAVIS Level-2B products and by GRACE/GRACE-FO
%   Level-2 files that are not in ICGEM layout:
%
%       <YAML header>
%       # End of YAML header
%       GRCOF2  n  m  C  S  sigC  sigS  t0  t1  flags     a FIELD
%       GRDOTA  n  m  Cdot  Sdot                          a RATE [1/yr]
%
%   This is NOT the ICGEM gfc layout, so shLowLevel.shReadGFC cannot read
%   it - and because the keyword is the only thing distinguishing a rate
%   model from a field, a gfc parser fed one of these fails outright
%   rather than returning something subtly wrong. GM and the reference
%   radius are taken from the YAML header
%   (earth_gravity_param / mean_equator_radius).
%
%   The GravIS auxiliary products this reads - the mean field, the
%   ICE-6G_D (VM5a) GIA rate model, and the monthly Level-2B solutions -
%   are what a user needs to reproduce published GravIS Level-3 mass
%   change series. A GRDOTA result drops straight into
%   shLowLevel.standardChain(GIA = ...), which expects a trend field in
%   [1/yr].
%
%   Inputs
%     filename   (1,1) string | char   path to the file; .gz is read
%                transparently
%
%   Options
%     Nmax (NaN)  truncate while reading (NaN: the file's own maximum
%             degree). A GIA model at degree 256 against a solution at
%             96 wastes memory and time
%
%   Outputs
%     out        (1,1) struct  fields:
%                  kind    (1,1) string  "GRCOF2" (field) | "GRDOTA" (rate)
%                  C, S    (nmax+1 x nmax+1) double  coefficients in the
%                          C(n+1, m+1) house layout; for GRDOTA these are
%                          rates per year
%                  sigmaC, sigmaS  (nmax+1 x nmax+1) double, or [] when
%                          the file carries none (GRDOTA never does)
%                  GM      (1,1) double  [m^3/s^2] from the header
%                  R       (1,1) double  [m] from the header
%                  nmax    (1,1) double  maximum degree actually read
%                  header  (1,1) string  the raw YAML header, kept so
%                          provenance is not lost on the way in
%
%   Errors
%     shLowLevel:readSHM:noHeaderEnd   no "# End of YAML header" line
%     shLowLevel:readSHM:noRecords     header present but no data records
%     shLowLevel:readSHM:mixedKinds    GRCOF2 and GRDOTA in one file
%
%   Example
%     gia = shLowLevel.readSHM("GRAVIS-2B_..._GIA_ICE-6G_D_VM5a_0001.gz", ...
%         Nmax = 96);
%     g = shCoefficients(gia.C, gia.S, GM = gia.GM, R = gia.R);
%     ts = shLowLevel.standardChain(folder, GIA = g);   % rates in 1/yr
%
%   See also shLowLevel.shReadGFC, shLowLevel.standardChain.
%
%   Developed by Matthias Weigelt with the help of Claude (Opus 5),
%   2026-08-11 (v3.3.0).
arguments
    filename {mustBeTextScalar}
    opts.Nmax (1,1) double = NaN
end
filename = char(filename);
if ~isfile(filename)
    error('shLowLevel:readSHM:noFile', 'File not found: %s', filename);
end
if endsWith(filename, ".gz", 'IgnoreCase', true)
    tmp = tempname;
    cl = onCleanup(@() rmIfExists(tmp)); %#ok<NASGU>
    gunzip(filename, tmp);
    d = dir(fullfile(tmp, '*'));
    d = d(~[d.isdir]);
    txt = fileread(fullfile(d(1).folder, d(1).name));
else
    txt = fileread(filename);
end
lines = strsplit(txt, newline);

iEnd = find(startsWith(strtrim(lines), '# End of YAML header'), 1);
if isempty(iEnd)
    error('shLowLevel:readSHM:noHeaderEnd', ...
        ['No "# End of YAML header" line in %s - this is not an SHM ' ...
         'file (ICGEM .gfc files are read by shLowLevel.shReadGFC).'], ...
        filename);
end
head = strjoin(lines(1:iEnd), newline);
body = lines(iEnd+1:end);

GM = headerValue(lines(1:iEnd), 'gravitational constant');
R = headerValue(lines(1:iEnd), 'equator radius');

isRec = startsWith(body, 'GRCOF2') | startsWith(body, 'GRDOTA');
rec = body(isRec);
if isempty(rec)
    error('shLowLevel:readSHM:noRecords', ...
        'No GRCOF2/GRDOTA records after the header in %s.', filename);
end
kinds = unique(extractBefore(string(rec(:)), 7));
if numel(kinds) > 1
    error('shLowLevel:readSHM:mixedKinds', ...
        ['%s mixes %s records - a field and a rate model cannot share ' ...
         'a file without their units becoming ambiguous.'], ...
        filename, strjoin(kinds, ' and '));
end
kind = kinds(1);

% bulk parse: skip the keyword, read the leading numeric fields, ignore
% the trailing epoch/flag columns. textscan does this in one pass; the
% GRCOF2 tail (t0 t1 flags) is not numeric throughout, so a plain sscanf
% over the block would misalign exactly the way a ragged gfc group does.
if kind == "GRCOF2"
    fmt = '%*s %f %f %f %f %f %f %*[^\n]';
    nCol = 6;
else
    fmt = '%*s %f %f %f %f %*[^\n]';
    nCol = 4;
end
blk = sprintf('%s\n', rec{:});
blk = strrep(blk, 'D', 'E');               % FORTRAN exponents, as in gfc
C6 = textscan(blk, fmt, 'CollectOutput', true);
V = C6{1};
if size(V, 1) ~= numel(rec) || size(V, 2) ~= nCol || any(~isfinite(V(:)))
    V = parseByLine(rec, nCol, filename);  % authoritative line parser
end

n = V(:,1); m = V(:,2);
nmaxFile = max(n);
nmax = opts.Nmax;
if ~isfinite(nmax), nmax = nmaxFile; end
keep = n <= nmax;
n = n(keep); m = m(keep); V = V(keep, :);

C = zeros(nmax+1); S = zeros(nmax+1);
lin = sub2ind(size(C), n+1, m+1);
C(lin) = V(:,3); S(lin) = V(:,4);
if nCol == 6
    sigmaC = zeros(nmax+1); sigmaS = zeros(nmax+1);
    sigmaC(lin) = V(:,5); sigmaS(lin) = V(:,6);
else
    sigmaC = []; sigmaS = [];
end
out = struct('kind', string(kind), 'C', C, 'S', S, ...
    'sigmaC', sigmaC, 'sigmaS', sigmaS, 'GM', GM, 'R', R, ...
    'nmax', nmax, 'header', string(head));
end

% ------------------------------------------------------------- helpers
function v = headerValue(head, what)
%HEADERVALUE The YAML puts "value :" a few lines below its long_name.
v = NaN;
k = find(contains(head, what), 1);
if isempty(k), return, end
for j = k:min(k+5, numel(head))
    t = regexp(head{j}, 'value\s*:\s*([-\d.EeDd+]+)', 'tokens', 'once');
    if ~isempty(t)
        v = str2double(strrep(t{1}, 'D', 'E'));
        return
    end
end
end

function V = parseByLine(rec, nCol, filename)
%PARSEBYLINE Authoritative fallback when the bulk block is not rectangular.
V = zeros(numel(rec), nCol);
for k = 1:numel(rec)
    line = strrep(regexprep(rec{k}, '^\S+\s+', ''), 'D', 'E');
    t = sscanf(line, '%f', nCol);
    if numel(t) < nCol
        error('shLowLevel:readSHM:badRecord', ...
            'Record %d of %s has %d numeric fields, expected %d.', ...
            k, filename, numel(t), nCol);
    end
    V(k, :) = t(:).';
end
end

function rmIfExists(d)
if isfolder(d), rmdir(d, 's'); elseif isfile(d), delete(d); end
end
