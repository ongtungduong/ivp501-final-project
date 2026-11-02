function varargout = main(keyPath, imagePaths, showFigures)
%MAIN He thong cham bai trac nghiem, chi dung MATLAB co ban (khong can toolbox).
%   main()                        cham du lieu mau trong thu muc samples
%   main('dap_an.csv', {'a.jpg', 'b.jpg'})
%   results = main(key, images, false)    khong hien hinh
%
%   Dap an la CSV hai cot cau,dap_an. Phieu in tu templates/answer_sheet.pdf.
%   Bang diem ghi ra scores.csv trong thu muc hien tai.

here = fileparts(mfilename('fullpath'));
if nargin < 1 || isempty(keyPath)
    keyPath = fullfile(here, 'samples', 'sample_answer_key.csv');
end
if nargin < 2 || isempty(imagePaths)
    imagePaths = {fullfile(here, 'samples', 'sample_submission.jpg')};
end
if ischar(imagePaths)
    imagePaths = {imagePaths};
end
if nargin < 3
    showFigures = usejava('desktop');
end

C = omrConstants();
key = loadAnswerKey(keyPath, C);
results = cell(1, numel(imagePaths));
for i = 1:numel(imagePaths)
    [~, stem, ext] = fileparts(imagePaths{i});
    name = [stem ext];
    try
        results{i} = gradeReading(name, readSheet(imagePaths{i}, C), key, C);
    catch err  % mot file loi khong duoc lam mat ket qua cua ca lop
        results{i} = emptyResult(name, C.REVIEW);
        results{i}.notes = {['Lỗi khi xử lý ảnh: ' err.message]};
    end
end
results = [results{:}];
results = noteDuplicateIds(results);

writeScores(results, 'scores.csv');
printScores(results);
if showFigures && ~isempty(results)
    showSheet(results(1), key, C);
end
if nargout > 0
    varargout{1} = results;
end
end


%% ---------- Bo cuc phieu (toa do tinh tu 0, giong src/omr_layout.py) ----------

function C = omrConstants()
C.PAGE_W = 1654;  % A4 o 200 DPI
C.PAGE_H = 2339;
C.NUM_QUESTIONS = 40;
C.CHOICES = 'ABCD';
C.ID_DIGITS = 6;
C.BUBBLE_RADIUS = 20;
C.MARKERS = [80 80; 1574 80; 1574 2259; 80 2259];  % TL, TR, BR, BL
C.MARKER_SIZE = 60;
C.BAR = [677 70 300 20];  % x, y, w, h: chi co o mep tren

C.MAX_SIDE = 3000;
C.MAX_CANDIDATES = 12;
C.BLANK_BELOW = 0.25;  % ti le diem den trong o
C.FILLED_ABOVE = 0.75;
C.DARK_PIXEL = 0.75;  % do sang so voi nen giay; toi hon muc nay la diem den
C.SOLID_MEAN = 0.65;  % o da to phai du dam
C.PAPER = 0.92;  % sang hon muc nay moi coi la giay sach
C.MAX_INNER_MARKS = 0.05;  % o "trong" phai sach ben trong vien in
C.MAX_DIRTY_OUTSIDE = 0.15;  % giay quanh o phai sach, neu khong co the la bong do
C.MAX_DARKNESS_GAP = 0.15;  % hai o cung to phai dam nhu nhau, khac nhieu la vet tay
C.MAX_MISSING_RINGS = 0.05;
C.MIN_SHARPNESS = 0.12;
C.RING_COVERAGE = 0.7;
C.SNAP = 8;  % px: sai so nan cuc bo toi da duoc bu lai

C.DONE = 'Đã chấm';
C.REVIEW = 'Cần xem lại';

% Mat na dung chung cho moi o
P = C.BUBBLE_RADIUS + 10;
[X, Y] = meshgrid(-P:P);
D = hypot(X, Y);
C.P = P;
C.CORE = D <= floor(C.BUBBLE_RADIUS * 0.7);
C.INNER = D <= C.BUBBLE_RADIUS - 4;
C.OUTSIDE = D >= C.BUBBLE_RADIUS + 4 & D <= P;

% Mau vien: vong duong o vien in, vong am ngay ben ngoai
T = C.BUBBLE_RADIUS + 7;
[X, Y] = meshgrid(-T:T);
D = hypot(X, Y);
ring = zeros(size(D));
ring(abs(D - (C.BUBBLE_RADIUS + 5)) <= 1.5) = -1;
ring(abs(D - C.BUBBLE_RADIUS) <= 1) = 1;
C.T = T;
C.RING = ring;
C.RING_ANGLES = linspace(0, 2 * pi, 37);
C.RING_ANGLES(end) = [];
end


function p = questionBubble(q, choiceIndex)
% Tam o cua cau q (1..40), lua chon choiceIndex (1..4)
col = floor((q - 1) / 10);
row = mod(q - 1, 10);
p = [250 + col * 350 + (choiceIndex - 1) * 70, 1000 + row * 110];
end


function p = idBubble(pos, digit)
% Tam o cua chu so thu pos (1..6), gia tri digit (0..9)
p = [1050 + (pos - 1) * 70, 260 + digit * 62];
end


%% ---------- Buoc 1: doc anh va tien xu ly ----------

function gray = loadGray(path, C)
% Doc anh thanh anh xam 0..255, gioi han kich thuoc. Anh xoay ngang duoc xu ly
% o buoc tim 4 o dinh vi, vi canh dai cua phieu luon la chieu doc.
try
    [img, map] = imread(path);
catch
    error('omr:unreadable', '%s', 'Không đọc được file ảnh');
end
if ~isempty(map)
    img = ind2rgb(img, map) * 255;
elseif isa(img, 'uint16')
    img = double(img) / 257;
elseif islogical(img)
    img = double(img) * 255;
else
    img = double(img);
end
if size(img, 3) >= 3
    gray = 0.299 * img(:, :, 1) + 0.587 * img(:, :, 2) + 0.114 * img(:, :, 3);
else
    gray = img(:, :, 1);
end
scale = C.MAX_SIDE / max(size(gray));
if scale < 1
    newSize = round(size(gray) * scale);
    if min(newSize) < 2
        error('omr:unreadable', '%s', 'Không đọc được file ảnh');
    end
    k = 2 * ceil(1 / scale) + 1;  % loc truoc khi thu nho de tranh rang cua
    gray = gaussBlur(gray, k);
    [X, Y] = meshgrid(linspace(1, size(gray, 2), newSize(2)), ...
                      linspace(1, size(gray, 1), newSize(1)));
    gray = interp2(gray, X, Y, 'linear');
end
end


function out = gaussBlur(img, k)
% Loc Gauss kich thuoc k, sigma theo cong thuc mac dinh cua OpenCV, bien nhan ban
sigma = 0.3 * ((k - 1) / 2 - 1) + 0.8;
r = (k - 1) / 2;
g = exp(-(-r:r)' .^ 2 / (2 * sigma ^ 2));
g = g / sum(g);
[n, c] = size(img);
padded = img([ones(1, r), 1:n, n * ones(1, r)], [ones(1, r), 1:c, c * ones(1, r)]);
out = conv2(g, g', padded, 'same');
out = out(r + 1:r + n, r + 1:r + c);
end


function binary = adaptiveBinary(gray)
% Anh xam -> loc nhieu -> phan nguong thich nghi (block lon hon duong kinh o tron)
blurred = gaussBlur(gray, 5);
binary = blurred <= gaussBlur(blurred, 101) - 10;
end


%% ---------- Buoc 2: tim 4 o dinh vi ----------

function comps = findCandidates(binary, C)
% Thanh phan lien thong gan vuong, dac, lon: ung vien o dinh vi.
% Moi cot duoc tach thanh cac doan lien tiep, roi noi doan chong nhau o hai cot canh nhau.
[~, c] = size(binary);
d = diff(double([false(1, c); binary; false(1, c)]), 1, 1);
[sr, sc] = find(d == 1);
[er, ~] = find(d == -1);
er = er - 1;
m = numel(sr);
comps = zeros(0, 3);
if m == 0
    return;
end

parent = 1:m;
j = 1;
for i = 1:m
    while j < i && (sc(j) < sc(i) - 1 || (sc(j) == sc(i) - 1 && er(j) < sr(i)))
        j = j + 1;
    end
    k = j;
    while k < i && sc(k) == sc(i) - 1 && sr(k) <= er(i)
        a = i;
        while parent(a) ~= a
            a = parent(a);
        end
        b = k;
        while parent(b) ~= b
            b = parent(b);
        end
        root = min(a, b);
        parent([a b i k]) = root;
        k = k + 1;
    end
end
for i = 1:m  % parent(i) <= i nen duyet tang dan la du
    parent(i) = parent(parent(i));
end
[~, ~, label] = unique(parent(:));

lens = er - sr + 1;
areas = accumarray(label, lens);
minArea = (max(size(binary)) / 200) ^ 2;
maxArea = 0.02 * numel(binary);
for id = find(areas(:)' >= minArea & areas(:)' <= maxArea)
    runs = find(label == id);
    x = [sc(runs); sc(runs)] - 1;
    y = [sr(runs); er(runs)] - 1;
    if ~isSquareLike(x, y, areas(id))
        continue;
    end
    cx = sum((sc(runs) - 1) .* lens(runs)) / areas(id);
    cy = sum(((sr(runs) + er(runs)) / 2 - 1) .* lens(runs)) / areas(id);
    comps(end + 1, :) = [areas(id), cx, cy];  %#ok<AGROW>
end
comps = sortrows(comps, -1);
comps = comps(1:min(size(comps, 1), C.MAX_CANDIDATES), :);
end


function ok = isSquareLike(x, y, area)
% Phoi canh manh lam o vuong thanh hinh binh hanh, nen do dac tinh theo bao loi
ok = false;
try
    hull = convhull(x, y);
catch
    return;  % cac diem thang hang
end
hx = x(hull);
hy = y(hull);
if area / polyarea(hx, hy) < 0.9
    return;
end
best = inf;
w = 0;
h = 0;
for i = 1:numel(hx) - 1  % hinh chu nhat nho nhat co mot canh trung canh bao loi
    a = atan2(hy(i + 1) - hy(i), hx(i + 1) - hx(i));
    u = hx * cos(a) + hy * sin(a);
    v = -hx * sin(a) + hy * cos(a);
    du = max(u) - min(u) + 1;
    dv = max(v) - min(v) + 1;
    if du * dv < best
        best = du * dv;
        w = du;
        h = dv;
    end
end
ok = w / h > 0.5 && w / h < 2 && area / best >= 0.7;
end


function corners = findMarkers(binary, C)
% Bo 4 o phai dung ti le phieu va khop thanh dinh huong
cands = findCandidates(binary, C);
n = size(cands, 1);
if n < 4
    error('omr:unreadable', '%s', 'Không tìm thấy 4 ô định vị');
end
combos = nchoosek(1:n, 4);
valid = {};
sizes = [];
for i = 1:size(combos, 1)
    set4 = cands(combos(i, :), :);
    if max(set4(:, 1)) / min(set4(:, 1)) > 2
        continue;
    end
    p = orderCorners(set4(:, 2:3));
    if isValidQuad(p, C) && barPresent(binary, p, C)
        valid{end + 1} = p;  %#ok<AGROW>
        sizes(end + 1) = norm(p(1, :) - p(3, :));  %#ok<AGROW>
    end
end
if isempty(valid)
    error('omr:unreadable', '%s', 'Không tìm thấy 4 ô định vị');
end
% Bo lon nhat la phieu that; cac o da to ben trong cung co the xep thanh bo gia
[~, order] = sort(sizes, 'descend');
corners = valid{order(1)};
for i = order(2:end)
    if ~any(inpolygon(valid{i}(:, 1), valid{i}(:, 2), corners(:, 1), corners(:, 2)))
        error('omr:unreadable', '%s', 'Ảnh có nhiều hơn một phiếu');
    end
end
end


function p = orderCorners(pts)
% Sap xep 4 goc theo vong, canh dai cua tu giac la chieu doc cua phieu
center = mean(pts, 1);
[~, idx] = sort(atan2(pts(:, 2) - center(2), pts(:, 1) - center(1)));
p = pts(idx, :);
if norm(p(1, :) - p(2, :)) > norm(p(2, :) - p(3, :))
    p = p([2 3 4 1], :);
end
end


function ok = isValidQuad(p, C)
% Tu giac loi, cac canh doi gan bang nhau, ti le gan voi ti le phieu
e = p([2 3 4 1], :) - p;
turns = e(:, 1) .* e([2 3 4 1], 2) - e(:, 2) .* e([2 3 4 1], 1);
sides = sqrt(sum(e .^ 2, 2));
ok = false;
if ~(all(turns > 0) || all(turns < 0)) || min(sides(1), sides(3)) < 100
    return;
end
if max(sides(1), sides(3)) / min(sides(1), sides(3)) > 1.5 || ...
        max(sides(2), sides(4)) / min(sides(2), sides(4)) > 1.5
    return;
end
ratio = (C.MARKERS(3, 2) - C.MARKERS(2, 2)) / (C.MARKERS(2, 1) - C.MARKERS(1, 1));
ok = abs((sides(2) + sides(4)) / (sides(1) + sides(3)) - ratio) / ratio < 0.35;
end


function ok = barPresent(binary, corners, C)
% Dung bo 4 o thi thanh dinh huong phai nam o mep tren hoac mep duoi
H = homography(C.MARKERS, corners);
b = C.BAR;
[X, Y] = meshgrid(b(1) + 20:b(1) + b(3) - 21, b(2) + 4:b(2) + b(4) - 5);
top = sampleDark(binary, H, X, Y);
bottom = sampleDark(binary, H, C.PAGE_W - 1 - X, C.PAGE_H - 1 - Y);
ok = max(top, bottom) > 0.7 && min(top, bottom) < 0.3;
end


function value = sampleDark(binary, H, X, Y)
[u, v] = applyHomography(H, X, Y);
col = round(u) + 1;
row = round(v) + 1;
inside = col >= 1 & col <= size(binary, 2) & row >= 1 & row <= size(binary, 1);
value = 0;
if any(inside(:))
    value = sum(binary(sub2ind(size(binary), row(inside), col(inside)))) / numel(X);
end
end


%% ---------- Buoc 3: bien doi phoi canh ----------

function H = homography(src, dst)
% Tu 4 cap diem giai he 8 an, duoc ma tran 3x3 dua src thanh dst
A = zeros(8, 8);
b = zeros(8, 1);
for i = 1:4
    x = src(i, 1);
    y = src(i, 2);
    A(2 * i - 1, :) = [x y 1 0 0 0 -x * dst(i, 1) -y * dst(i, 1)];
    A(2 * i, :) = [0 0 0 x y 1 -x * dst(i, 2) -y * dst(i, 2)];
    b(2 * i - 1) = dst(i, 1);
    b(2 * i) = dst(i, 2);
end
H = reshape([A \ b; 1], 3, 3)';
end


function [u, v] = applyHomography(H, X, Y)
w = H(3, 1) * X + H(3, 2) * Y + H(3, 3);
u = (H(1, 1) * X + H(1, 2) * Y + H(1, 3)) ./ w;
v = (H(2, 1) * X + H(2, 2) * Y + H(2, 3)) ./ w;
end


function warped = warpSheet(gray, corners, C)
% Voi moi diem cua khung chuan, tinh vi tri tuong ung tren anh chup roi noi suy
[X, Y] = meshgrid(0:C.PAGE_W - 1, 0:C.PAGE_H - 1);
[u, v] = applyHomography(homography(C.MARKERS, corners), X, Y);
warped = interp2(gray, u + 1, v + 1, 'linear', 0);
end


function warped = fixOrientation(warped, C)
% Dua vao thanh den chi co o mep tren de xac dinh chieu phieu, xoay 180 do neu nguoc
b = C.BAR;
rows = b(2) + 1:b(2) + b(4);
cols = b(1) + 1:b(1) + b(3);
flipped = rot90(warped, 2);
top = mean(mean(warped(rows, cols)));
bottom = mean(mean(flipped(rows, cols)));
if min(top, bottom) > 0.6 * max(top, bottom)
    error('omr:unreadable', '%s', 'Không xác định được chiều phiếu');
end
if bottom < top
    warped = flipped;
end
end


%% ---------- Buoc 4: doc o to ----------

function norm01 = normalizeLight(warped)
% Chia cho nen giay uoc luong duoc (phep dong hinh thai) de khu anh sang khong deu
k = 61;
blurred = gaussBlur(warped, 5);
background = -maxFilter(-maxFilter(blurred, k), k);
norm01 = blurred ./ max(background, 1);
end


function out = maxFilter(A, k)
out = maxFilterColumns(maxFilterColumns(A, k)', k)';
end


function out = maxFilterColumns(A, k)
% Bo loc cuc dai cua so k tren moi cot, thuat toan van Herk: chia khoi va cummax hai chieu
r = (k - 1) / 2;
[n, c] = size(A);
P = A([ones(1, r), 1:n, n * ones(1, r)], :);
total = ceil(size(P, 1) / k) * k;
P = [P; repmat(P(end, :), total - size(P, 1), 1)];
B = reshape(P, k, []);
forward = reshape(cummax(B, 1), total, c);
backward = reshape(flipud(cummax(flipud(B), 1)), total, c);
out = max(backward(1:n, :), forward(k:n + k - 1, :));
end


function p = patchAt(img, center, P)
p = img(center(2) + 1 - P:center(2) + 1 + P, center(1) + 1 - P:center(1) + 1 + P);
end


function p = snapCenter(binary, center, C)
% Can lai tam o theo vien in gan nhat, bu sai so phoi canh va giay cong
window = double(patchAt(binary, center, C.T + C.SNAP));
score = conv2(window, rot90(C.RING, 2), 'valid');
[best, idx] = max(score(:));
p = center;
if best > 0
    [dy, dx] = ind2sub(size(score), idx);
    p = center + [dx - 1 - C.SNAP, dy - 1 - C.SNAP];
end
end


function state = classifyRatio(ratio, C)
if ratio < C.BLANK_BELOW
    state = 'blank';
elseif ratio > C.FILLED_ABOVE
    state = 'filled';
else
    state = 'uncertain';
end
end


function state = bubbleState(norm01, center, C)
% "Trong" can bang chung: ben trong vien in sach va giay xung quanh sach
patch = patchAt(norm01, center, C.P);
core = patch(C.CORE);
if mean(patch(C.OUTSIDE) < C.PAPER) > C.MAX_DIRTY_OUTSIDE
    state = 'uncertain';
    return;
end
state = classifyRatio(mean(core < C.DARK_PIXEL), C);
if strcmp(state, 'filled')
    if mean(core) > C.SOLID_MEAN
        state = 'uncertain';
    end
elseif mean(patch(C.INNER) < C.PAPER) > C.MAX_INNER_MARKS
    state = 'uncertain';
end
end


function ok = ringVisible(binary, center, C)
% Vien in cua o co nam dung cho khong? Xet 36 huong quanh tam, cho phep lech 4 px
seen = 0;
for a = C.RING_ANGLES
    for r = C.BUBBLE_RADIUS - 4:C.BUBBLE_RADIUS + 4
        if binary(fix(center(2) + r * sin(a)) + 1, fix(center(1) + r * cos(a)) + 1)
            seen = seen + 1;
            break;
        end
    end
end
ok = seen / numel(C.RING_ANGLES) >= C.RING_COVERAGE;
end


function state = bubbleFinal(norm01, binary, center, C)
% O trong ma khong thay vien (bi loa che) thi khong the coi la chac chan trong
center = snapCenter(binary, center, C);
state = bubbleState(norm01, center, C);
if strcmp(state, 'blank') && ~ringVisible(binary, center, C)
    state = 'uncertain';
end
end


function value = edgeSharpness(warped, C)
% Do doc lon nhat tai canh trai cac o dinh vi, chia cho do tuong phan; canh net ~ 0.5
half = C.MARKER_SIZE / 2;
value = inf;
for i = 1:4
    x = C.MARKERS(i, 1);
    y = C.MARKERS(i, 2);
    profile = mean(warped(y - 14:y + 15, x - half - 24:x - half + 25), 1);
    contrast = max(max(profile) - min(profile), 1);
    value = min(value, max(abs(diff(profile))) / contrast);
end
end


function problems = checkQuality(warped, binary, C)
% Bao anh mo qua do net cua canh; bao loa/lech khi khong thay vien cua nhieu o
problems = {};
if edgeSharpness(warped, C) < C.MIN_SHARPNESS
    problems{end + 1} = 'Ảnh bị mờ';
end
missing = 0;
total = C.NUM_QUESTIONS * numel(C.CHOICES) + C.ID_DIGITS * 10;
for q = 1:C.NUM_QUESTIONS
    for c = 1:numel(C.CHOICES)
        missing = missing + ~ringVisible(binary, snapCenter(binary, questionBubble(q, c), C), C);
    end
end
for pos = 1:C.ID_DIGITS
    for d = 0:9
        missing = missing + ~ringVisible(binary, snapCenter(binary, idBubble(pos, d), C), C);
    end
end
if missing / total > C.MAX_MISSING_RINGS
    problems{end + 1} = 'Ảnh bị lóa hoặc lưới ô bị lệch';
end
end


function [studentId, problems] = readStudentId(norm01, binary, C)
digits = '';
problems = {};
for pos = 1:C.ID_DIGITS
    filled = [];
    unsure = false;
    for d = 0:9
        state = bubbleFinal(norm01, binary, idBubble(pos, d), C);
        filled = [filled d(strcmp(state, 'filled'))];  %#ok<AGROW>
        unsure = unsure || strcmp(state, 'uncertain');
    end
    if unsure || numel(filled) ~= 1
        problems{end + 1} = sprintf('Mã học sinh: chữ số thứ %d không đọc được', pos);  %#ok<AGROW>
    else
        digits(end + 1) = char('0' + filled);  %#ok<AGROW>
    end
end
studentId = '';
if isempty(problems)
    studentId = digits;
end
end


function uneven = unevenMarks(norm01, binary, q, marked, C)
% Hai o to dam khac han nhau: o nhat hon co the la vet tay chua sach
uneven = false;
if numel(marked) < 2
    return;
end
means = zeros(1, numel(marked));
for i = 1:numel(marked)
    c = find(C.CHOICES == marked(i));
    patch = patchAt(norm01, snapCenter(binary, questionBubble(q, c), C), C.P);
    means(i) = mean(patch(C.CORE));
end
uneven = max(means) - min(means) > C.MAX_DARKNESS_GAP;
end


function r = readSheet(path, C)
% Doc mot anh bai lam; anh khong doc duoc thi ghi ly do vao problems
r = struct('studentId', '', 'idProblems', {{}}, 'marks', {cell(1, C.NUM_QUESTIONS)}, ...
           'uncertain', [], 'problems', {{}}, 'steps', {{}}, 'corners', [], 'warped', []);
try
    gray = loadGray(path, C);
    r.steps(end + 1, :) = {'Ảnh xám', gray};
    binary = adaptiveBinary(gray);
    r.steps(end + 1, :) = {'Phân ngưỡng thích nghi', double(binary) * 255};
    r.corners = findMarkers(binary, C);
    r.steps(end + 1, :) = {'Tìm 4 ô định vị', gray};
    warped = fixOrientation(warpSheet(gray, r.corners, C), C);
catch err
    if ~strcmp(err.identifier, 'omr:unreadable')
        rethrow(err);
    end
    r.problems{end + 1} = err.message;
    return;
end
r.warped = warped;
r.steps(end + 1, :) = {'Nắn phối cảnh', warped};
wbinary = adaptiveBinary(warped);
norm01 = normalizeLight(warped);
r.steps(end + 1, :) = {'Khử ánh sáng', min(norm01, 1) * 255};
r.problems = checkQuality(warped, wbinary, C);
[r.studentId, r.idProblems] = readStudentId(norm01, wbinary, C);
for q = 1:C.NUM_QUESTIONS
    marked = '';
    unsure = false;
    for c = 1:numel(C.CHOICES)
        state = bubbleFinal(norm01, wbinary, questionBubble(q, c), C);
        if strcmp(state, 'filled')
            marked(end + 1) = C.CHOICES(c);  %#ok<AGROW>
        end
        unsure = unsure || strcmp(state, 'uncertain');
    end
    r.marks{q} = marked;
    if unsure || unevenMarks(norm01, wbinary, q, marked, C)
        r.uncertain(end + 1) = q;
    end
end
end


%% ---------- Buoc 5: dap an va cham diem ----------

function key = loadAnswerKey(path, C)
% Doc CSV hai cot cau,dap_an; chap nhan file luu tu Excel (BOM, dau ;, chu thuong)
fid = fopen(path, 'rb');
if fid < 0
    keyError('Không đọc được file đáp án');
end
bytes = fread(fid, inf, 'uint8=>uint8')';
fclose(fid);
if numel(bytes) >= 3 && isequal(bytes(1:3), uint8([239 187 191]))
    bytes = bytes(4:end);
end
lines = regexp(char(bytes), '\r\n|\n|\r', 'split');
lines = strtrim(lines);
lines = lines(~cellfun(@isempty, lines));
if ~isempty(lines) && strncmpi(lines{1}, 'sep=', 4)
    lines = lines(2:end);
end
if isempty(lines)
    keyError('File đáp án trống');
end
delim = ',';
if any(lines{1} == ';')
    delim = ';';
end
rows = {};
numbers = [];
for i = 1:numel(lines)
    cells = strtrim(strsplit(strrep(lines{i}, '"', ''), delim, 'CollapseDelimiters', false));
    while ~isempty(cells) && isempty(cells{end})
        cells(end) = [];
    end
    if ~isempty(cells)  % Excel hay de lai dong toan dau phan cach
        rows{end + 1} = cells;  %#ok<AGROW>
        numbers(end + 1) = i;  %#ok<AGROW>
    end
end
if isempty(rows) || numel(rows{1}) ~= 2 || ~strcmpi(rows{1}{1}, 'cau') || ~strcmpi(rows{1}{2}, 'dap_an')
    keyError('Dòng đầu của file đáp án phải là: cau,dap_an');
end
key = '';
for i = 2:numel(rows)
    row = rows{i};
    if numel(row) ~= 2 || isempty(regexp(row{1}, '^[0-9]+$', 'once'))
        keyError(sprintf('Dòng %d sai định dạng', numbers(i)));
    end
    answer = upper(row{2});
    if numel(answer) ~= 1 || ~any(C.CHOICES == answer)
        keyError(sprintf('Dòng %d: đáp án phải là một trong A, B, C, D', numbers(i)));
    end
    if str2double(row{1}) ~= numel(key) + 1
        keyError(sprintf('Dòng %d: số câu phải liên tục từ 1', numbers(i)));
    end
    key(end + 1) = answer;  %#ok<AGROW>
end
if isempty(key) || numel(key) > C.NUM_QUESTIONS
    keyError(sprintf('Đáp án phải có từ 1 đến %d câu', C.NUM_QUESTIONS));
end
end


function keyError(message)
error('omr:key', '%s', ['Lỗi file đáp án: ' message]);
end


function result = emptyResult(name, status)
result = struct('filename', name, 'status', status, 'studentId', '', 'correct', [], ...
                'score', [], 'notes', {{}}, 'marks', {{}}, 'warped', [], 'steps', {{}}, 'corners', []);
end


function result = gradeReading(name, reading, key, C)
% Bai doc khong chac chan thi "Can xem lai", khong bao gio cho diem
result = emptyResult(name, C.DONE);
result.studentId = reading.studentId;
result.marks = reading.marks;
result.warped = reading.warped;
result.steps = reading.steps;
result.corners = reading.corners;
N = numel(key);
notes = [reading.problems(:)', reading.idProblems(:)'];
unsure = reading.uncertain(reading.uncertain <= N);
if ~isempty(unsure)
    notes{end + 1} = ['Câu không đọc chắc chắn: ' joinNumbers(unsure)];
end
if ~isempty(notes)
    result.status = C.REVIEW;
    result.notes = notes;
    return;
end
counts = cellfun(@numel, reading.marks(1:N));
blank = find(counts == 0);
multi = find(counts > 1);
if ~isempty(blank)
    notes{end + 1} = ['Câu bỏ trống: ' joinNumbers(blank)];
end
if ~isempty(multi)
    notes{end + 1} = ['Câu tô nhiều ô: ' joinNumbers(multi)];
end
correct = 0;
for q = 1:N
    correct = correct + strcmp(reading.marks{q}, key(q));
end
result.correct = correct;
result.score = round(correct / N * 10 * 100) / 100;
result.notes = notes;
end


function text = joinNotes(notes)
text = '';
if ~isempty(notes)
    text = strjoin(notes, '; ');
end
end


function text = joinNumbers(values)
text = strjoin(arrayfun(@num2str, values, 'UniformOutput', false), ', ');
end


function results = noteDuplicateIds(results)
ids = {results.studentId};
for i = 1:numel(results)
    if ~isempty(ids{i}) && sum(strcmp(ids, ids{i})) > 1
        results(i).notes{end + 1} = ['Trùng mã học sinh ' ids{i}];
    end
end
end


%% ---------- Xuat ket qua ----------

function writeScores(results, path)
% Ghi UTF-8 co BOM de Excel hien dung tieng Viet
fid = fopen(path, 'wb');
if fid < 0
    error('omr:output', 'Không ghi được file %s', path);
end
fwrite(fid, uint8([239 187 191]), 'uint8');
writeLine(fid, 'ten_file,ma_hoc_sinh,so_cau_dung,diem,trang_thai,ghi_chu');
for r = results
    fields = {r.filename, r.studentId, numberText(r.correct), numberText(r.score), r.status, ...
              joinNotes(r.notes)};
    writeLine(fid, strjoin(cellfun(@csvCell, fields, 'UniformOutput', false), ','));
end
fclose(fid);
end


function writeLine(fid, text)
fwrite(fid, unicode2native([text char(10)], 'UTF-8'), 'uint8');
end


function text = csvCell(value)
text = value;
if any(value == ',' | value == '"')
    text = ['"' strrep(value, '"', '""') '"'];
end
end


function text = numberText(value)
text = '';
if ~isempty(value)
    text = num2str(value);
end
end


function printScores(results)
fprintf('%-30s %-8s %-6s %-6s %-14s %s\n', 'Tên file', 'Mã HS', 'Đúng', 'Điểm', 'Trạng thái', 'Ghi chú');
for r = results
    fprintf('%-30s %-8s %-6s %-6s %-14s %s\n', r.filename, r.studentId, numberText(r.correct), ...
            numberText(r.score), r.status, joinNotes(r.notes));
end
fprintf('Đã ghi bảng điểm: %s\n', fullfile(pwd, 'scores.csv'));
end


function showSheet(result, key, C)
% Hien cac buoc xu ly va anh danh dau cua mot bai
figure('Name', ['Các bước: ' result.filename]);
for i = 1:size(result.steps, 1)
    subplot(2, 3, i);
    imagesc(result.steps{i, 2}, [0 255]);
    colormap(gray(256));
    axis image off;
    title(result.steps{i, 1});
    if strcmp(result.steps{i, 1}, 'Tìm 4 ô định vị')
        hold on;
        plot(result.corners(:, 1) + 1, result.corners(:, 2) + 1, 'ro', 'MarkerSize', 12, 'LineWidth', 2);
        hold off;
    end
end
if isempty(result.warped)
    return;
end
figure('Name', ['Đánh dấu: ' result.filename]);
imagesc(result.warped, [0 255]);
colormap(gray(256));
axis image off;
hold on;
theta = linspace(0, 2 * pi, 60);
circleX = (C.BUBBLE_RADIUS + 6) * cos(theta);
circleY = (C.BUBBLE_RADIUS + 6) * sin(theta);
for q = 1:numel(key)  % xanh la dap an dung, do la o to sai
    p = questionBubble(q, find(C.CHOICES == key(q))) + 1;
    plot(p(1) + circleX, p(2) + circleY, 'g-', 'LineWidth', 2);
    marked = result.marks{q};
    wrong = marked(marked ~= key(q));
    for m = wrong
        p = questionBubble(q, find(C.CHOICES == m)) + 1;
        plot(p(1) + circleX, p(2) + circleY, 'r-', 'LineWidth', 2);
    end
end
hold off;
title(sprintf('%s - điểm: %s', result.status, numberText(result.score)));
end
