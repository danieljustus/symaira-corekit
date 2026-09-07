// Command publicapi records the exported Go API of the pinned CoreKit oracle.
package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"go/ast"
	"go/token"
	"go/types"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"golang.org/x/tools/go/packages"
)

const (
	modulePath         = "github.com/danieljustus/symaira-corekit"
	oracleCommit       = "f3d3eb79b9b1f31b4f973d2ed518a8292cedf588"
	oracleSourceDigest = "ab38c1cc4d2f91026e1d6836e1138388fd683a789ab8f104269d019c3caff95c"
)

type snapshot struct {
	SchemaVersion int               `json:"schema_version"`
	OracleCommit  string            `json:"oracle_commit"`
	Module        string            `json:"module"`
	GOOS          string            `json:"goos"`
	GOARCH        string            `json:"goarch"`
	Packages      []packageSnapshot `json:"packages"`
}

type packageSnapshot struct {
	Path         string                `json:"path"`
	Name         string                `json:"name"`
	Doc          string                `json:"doc,omitempty"`
	Declarations []declarationSnapshot `json:"declarations"`
}

type declarationSnapshot struct {
	Kind      string           `json:"kind"`
	Name      string           `json:"name"`
	Signature string           `json:"signature"`
	Value     string           `json:"value,omitempty"`
	Doc       string           `json:"doc,omitempty"`
	Methods   []memberSnapshot `json:"methods,omitempty"`
	Fields    []memberSnapshot `json:"fields,omitempty"`
}

type memberSnapshot struct {
	Name      string `json:"name"`
	Signature string `json:"signature"`
	Embedded  bool   `json:"embedded,omitempty"`
	Tag       string `json:"tag,omitempty"`
	Doc       string `json:"doc,omitempty"`
}

func main() {
	repo := flag.String("repo", ".", "path to the extracted oracle repository")
	goos := flag.String("goos", "", "target operating system")
	goarch := flag.String("goarch", "amd64", "target architecture")
	flag.Parse()
	if *goos == "" {
		fatal("goos is required")
	}
	if err := verifyOracleSource(*repo); err != nil {
		fatal("verify oracle source: %v", err)
	}

	cfg := &packages.Config{
		Mode: packages.NeedName | packages.NeedFiles | packages.NeedCompiledGoFiles |
			packages.NeedImports | packages.NeedDeps | packages.NeedTypes |
			packages.NeedSyntax | packages.NeedTypesInfo |
			packages.NeedModule,
		Dir:  *repo,
		Env:  targetEnv(*goos, *goarch),
		Fset: token.NewFileSet(),
	}
	loaded, err := packages.Load(cfg, "./...")
	if err != nil {
		fatal("load packages: %v", err)
	}
	if packages.PrintErrors(loaded) > 0 {
		fatal("package loading failed")
	}

	out := snapshot{SchemaVersion: 1, OracleCommit: oracleCommit, Module: modulePath, GOOS: *goos, GOARCH: *goarch}
	for _, pkg := range loaded {
		if !isPublicPackage(pkg.PkgPath) {
			continue
		}
		out.Packages = append(out.Packages, buildPackage(pkg))
	}
	sort.Slice(out.Packages, func(i, j int) bool { return out.Packages[i].Path < out.Packages[j].Path })
	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(out); err != nil {
		fatal("encode snapshot: %v", err)
	}
}

func verifyOracleSource(root string) error {
	var paths []string
	err := filepath.WalkDir(root, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			return nil
		}
		relative, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		relative = filepath.ToSlash(relative)
		if ownedOraclePath(relative) {
			paths = append(paths, relative)
		}
		return nil
	})
	if err != nil {
		return err
	}
	sort.Strings(paths)
	digest := sha256.New()
	for _, relative := range paths {
		content, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(relative)))
		if err != nil {
			return err
		}
		content = bytes.ReplaceAll(content, []byte("\r\n"), []byte("\n"))
		_, _ = digest.Write([]byte(relative))
		_, _ = digest.Write([]byte{0})
		_, _ = digest.Write(content)
		_, _ = digest.Write([]byte{0})
	}
	actual := hex.EncodeToString(digest.Sum(nil))
	if actual != oracleSourceDigest {
		return fmt.Errorf("source digest mismatch: expected %s, got %s", oracleSourceDigest, actual)
	}
	return nil
}

func ownedOraclePath(path string) bool {
	if strings.HasSuffix(path, ".go") && !strings.HasSuffix(path, "_test.go") {
		return true
	}
	if strings.HasPrefix(path, "contracts/") && strings.HasSuffix(path, ".json") {
		return true
	}
	return strings.Contains(path, "/testdata/") &&
		(strings.HasSuffix(path, ".json") || strings.HasSuffix(path, ".sql"))
}

func targetEnv(goos, goarch string) []string {
	blocked := map[string]bool{"GOOS": true, "GOARCH": true, "CGO_ENABLED": true}
	env := make([]string, 0, len(os.Environ())+3)
	for _, pair := range os.Environ() {
		name, _, _ := strings.Cut(pair, "=")
		if !blocked[name] {
			env = append(env, pair)
		}
	}
	return append(env, "GOOS="+goos, "GOARCH="+goarch, "CGO_ENABLED=0")
}

func isPublicPackage(path string) bool {
	if path != modulePath && !strings.HasPrefix(path, modulePath+"/") {
		return false
	}
	rel := strings.TrimPrefix(strings.TrimPrefix(path, modulePath), "/")
	for _, part := range strings.Split(rel, "/") {
		if part == "internal" || part == "cmd" || part == "scripts" {
			return false
		}
	}
	return true
}

func buildPackage(pkg *packages.Package) packageSnapshot {
	docs, packageDoc := collectDocs(pkg.Syntax)
	result := packageSnapshot{Path: pkg.PkgPath, Name: pkg.Name, Doc: packageDoc, Declarations: []declarationSnapshot{}}
	scope := pkg.Types.Scope()
	for _, name := range scope.Names() {
		if !ast.IsExported(name) {
			continue
		}
		obj := scope.Lookup(name)
		decl := declarationSnapshot{
			Kind: kindOf(obj), Name: name,
			Signature: types.ObjectString(obj, qualifier),
			Doc:       docs[name],
		}
		if constant, ok := obj.(*types.Const); ok {
			decl.Value = constant.Val().ExactString()
		}
		if typeName, ok := obj.(*types.TypeName); ok {
			decl.Methods = exportedMethods(typeName.Type(), typeName.Name(), docs)
			decl.Fields = exportedFields(typeName.Type(), typeName.Name(), docs)
		}
		result.Declarations = append(result.Declarations, decl)
	}
	return result
}

func kindOf(obj types.Object) string {
	switch obj.(type) {
	case *types.Const:
		return "const"
	case *types.Func:
		return "func"
	case *types.TypeName:
		return "type"
	case *types.Var:
		return "var"
	default:
		return fmt.Sprintf("%T", obj)
	}
}

func qualifier(pkg *types.Package) string { return pkg.Path() }

func exportedMethods(typ types.Type, typeName string, docs map[string]string) []memberSnapshot {
	named, ok := types.Unalias(typ).(*types.Named)
	if !ok {
		return nil
	}
	methodType := types.Type(named)
	if _, isInterface := named.Underlying().(*types.Interface); !isInterface {
		methodType = types.NewPointer(named)
	}
	set := types.NewMethodSet(methodType)
	var result []memberSnapshot
	for i := 0; i < set.Len(); i++ {
		method := set.At(i).Obj()
		if !method.Exported() {
			continue
		}
		docKey := typeName + "." + method.Name()
		if signature, ok := method.Type().(*types.Signature); ok && signature.Recv() != nil {
			if receiver := namedTypeName(signature.Recv().Type()); receiver != "" {
				docKey = receiver + "." + method.Name()
			}
		}
		result = append(result, memberSnapshot{
			Name: method.Name(), Signature: types.ObjectString(method, qualifier),
			Doc: docs[docKey],
		})
	}
	sort.Slice(result, func(i, j int) bool { return result[i].Name < result[j].Name })
	return result
}

func exportedFields(typ types.Type, typeName string, docs map[string]string) []memberSnapshot {
	named, ok := types.Unalias(typ).(*types.Named)
	if !ok {
		return nil
	}
	var result []memberSnapshot
	switch value := named.Underlying().(type) {
	case *types.Struct:
		for i := 0; i < value.NumFields(); i++ {
			field := value.Field(i)
			if !field.Exported() {
				continue
			}
			result = append(result, memberSnapshot{
				Name: field.Name(), Signature: types.TypeString(field.Type(), qualifier),
				Embedded: field.Embedded(), Tag: value.Tag(i), Doc: docs[typeName+"."+field.Name()],
			})
		}
	}
	sort.Slice(result, func(i, j int) bool { return result[i].Name < result[j].Name })
	return result
}

func namedTypeName(typ types.Type) string {
	if pointer, ok := typ.(*types.Pointer); ok {
		typ = pointer.Elem()
	}
	if named, ok := types.Unalias(typ).(*types.Named); ok {
		return named.Obj().Name()
	}
	return ""
}

func collectDocs(files []*ast.File) (map[string]string, string) {
	docs := map[string]string{}
	var packageDocs []string
	for _, file := range files {
		if file.Doc != nil {
			packageDocs = append(packageDocs, cleanDoc(file.Doc.Text()))
		}
		for _, declaration := range file.Decls {
			switch decl := declaration.(type) {
			case *ast.FuncDecl:
				if decl.Name.IsExported() && decl.Doc != nil {
					key := decl.Name.Name
					if decl.Recv != nil && len(decl.Recv.List) > 0 {
						if receiver := receiverName(decl.Recv.List[0].Type); receiver != "" {
							key = receiver + "." + key
						}
					}
					docs[key] = cleanDoc(decl.Doc.Text())
				}
			case *ast.GenDecl:
				for _, spec := range decl.Specs {
					switch item := spec.(type) {
					case *ast.TypeSpec:
						if item.Name.IsExported() {
							docs[item.Name.Name] = specDoc(item.Doc, decl.Doc)
							collectFieldDocs(docs, item.Name.Name, item.Type)
						}
					case *ast.ValueSpec:
						for _, name := range item.Names {
							if name.IsExported() {
								docs[name.Name] = specDoc(item.Doc, decl.Doc)
							}
						}
					}
				}
			}
		}
	}
	sort.Strings(packageDocs)
	return docs, strings.Join(packageDocs, "\n")
}

func collectFieldDocs(docs map[string]string, typeName string, expression ast.Expr) {
	var fields *ast.FieldList
	switch value := expression.(type) {
	case *ast.StructType:
		fields = value.Fields
	case *ast.InterfaceType:
		fields = value.Methods
	}
	if fields == nil {
		return
	}
	for _, field := range fields.List {
		doc := specDoc(field.Doc, field.Comment)
		for _, name := range field.Names {
			if name.IsExported() {
				docs[typeName+"."+name.Name] = doc
			}
		}
	}
}

func receiverName(expression ast.Expr) string {
	switch value := expression.(type) {
	case *ast.Ident:
		return value.Name
	case *ast.StarExpr:
		return receiverName(value.X)
	case *ast.IndexExpr:
		return receiverName(value.X)
	case *ast.IndexListExpr:
		return receiverName(value.X)
	default:
		return ""
	}
}

func specDoc(primary, fallback *ast.CommentGroup) string {
	if primary != nil {
		return cleanDoc(primary.Text())
	}
	if fallback != nil {
		return cleanDoc(fallback.Text())
	}
	return ""
}

func cleanDoc(value string) string { return strings.TrimSpace(strings.ReplaceAll(value, "\r\n", "\n")) }

func fatal(format string, args ...any) {
	_, _ = fmt.Fprintf(os.Stderr, "publicapi: "+format+"\n", args...)
	os.Exit(1)
}
