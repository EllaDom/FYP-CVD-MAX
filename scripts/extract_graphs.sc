import java.io.PrintWriter
import java.io.File
import io.joern.dataflowengineoss.language._

val cpgFile = sys.env("CPG_FILE")
val split   = sys.env("SPLIT")

importCpg(cpgFile, "project")

// ✅ FIXED PATH
val astDir = s"workspace/graphs/$split/ast"
val cfgDir = s"workspace/graphs/$split/cfg"
val pdgDir = s"workspace/graphs/$split/pdg"

new File(astDir).mkdirs()
new File(cfgDir).mkdirs()
new File(pdgDir).mkdirs()

// ✅ FIXED CLEAN FUNCTION
def clean(s: String) =
  Option(s).getOrElse("")
    .replace("\\", "\\\\")
    .replace("\"","'")
    .replace("\n"," ")
    .replace("\r"," ")
    .replace("\t"," ")

// Safe filename
def safeIdx(fileName: String, methodId: Long): String = {
  val base = fileName.replace("\\","/").split("/").last.replace(".c","")
  val cleaned = base.replaceAll("[<>:\"/\\\\|?*]", "")
  if(cleaned.isEmpty) s"method_$methodId" else cleaned
}

cpg.method
  .filterNot(m => m == null || m.name == "<global>")
  .foreach { m =>

    val fileNameOpt = Option(m.file).flatMap(f => f.name.headOption)
    val fileName = fileNameOpt.getOrElse("unknown.c")

    if (m.ast.isEmpty || m.cfgNode.isEmpty) {
      println(s"[WARN] Skipping method '${m.name}' in file '$fileName'")
    } else {

      val idx = safeIdx(fileName, m.id)

      // ---------------- AST ----------------
      val astNodeList = m.ast.l
      val astNodeIds  = astNodeList.map(_.id).toSet

      val astNodes = astNodeList.map { n =>
        s"""{
"id": ${n.id},
"label": "${clean(n.label)}",
"code": "${clean(n.code)}",
"line": ${n.lineNumber.getOrElse(-1)},
"column": ${n.columnNumber.getOrElse(-1)}
}"""
      }

      val astEdges = astNodeList.flatMap { n =>
        n.astChildren.filter(c => astNodeIds.contains(c.id)).map { c =>
          s"""{
"source": ${n.id},
"target": ${c.id},
"type": "AST"
}"""
        }
      }

      val astJson =
s"""{
"method": "${clean(m.name)}",
"id": ${m.id},
"nodes": [
${astNodes.mkString(",")}
],
"edges": [
${astEdges.mkString(",")}
]
}"""

      val astFile = new PrintWriter(new File(s"$astDir/$idx.json"))
      astFile.write(astJson)
      astFile.close()

      // ---------------- CFG ----------------
      val cfgNodeList = m.cfgNode.l.distinct
      val cfgNodeIds  = cfgNodeList.map(_.id).toSet

      val cfgNodes = cfgNodeList.map { n =>
        s"""{
"id": ${n.id},
"label": "${clean(n.label)}",
"code": "${clean(n.code)}",
"line": ${n.lineNumber.getOrElse(-1)},
"column": ${n.columnNumber.getOrElse(-1)}
}"""
      }

      val cfgEdges = cfgNodeList.flatMap { n =>
        n.cfgNext.filter(dst => cfgNodeIds.contains(dst.id)).map { dst =>
          s"""{
"source": ${n.id},
"target": ${dst.id},
"type": "CFG"
}"""
        }
      }.distinct

      val cfgJson =
s"""{
"method": "${clean(m.name)}",
"id": ${m.id},
"nodes": [
${cfgNodes.mkString(",")}
],
"edges": [
${cfgEdges.mkString(",")}
]
}"""

      val cfgFile = new PrintWriter(new File(s"$cfgDir/$idx.json"))
      cfgFile.write(cfgJson)
      cfgFile.close()

      // ---------------- PDG ----------------
      val pdgNodeList = cfgNodeList

      val pdgNodes = pdgNodeList.map { n =>
        s"""{
"id": ${n.id},
"label": "${clean(n.label)}",
"code": "${clean(n.code)}",
"line": ${n.lineNumber.getOrElse(-1)},
"column": ${n.columnNumber.getOrElse(-1)}
}"""
      }

      val pdgEdges = pdgNodeList.flatMap { n =>
        n.outE
         .filter(e => e.label == "REACHING_DEF" || e.label == "CDG" || e.label == "DDG")
         .map { e =>
           s"""{
"source": ${e.src.id},
"target": ${e.dst.id},
"type": "${e.label}"
}"""
         }
      }.distinct

      val pdgJson =
s"""{
"method": "${clean(m.name)}",
"id": ${m.id},
"nodes": [
${pdgNodes.mkString(",")}
],
"edges": [
${pdgEdges.mkString(",")}
]
}"""

      val pdgFile = new PrintWriter(new File(s"$pdgDir/$idx.json"))
      pdgFile.write(pdgJson)
      pdgFile.close()
    }
  }

println("AST + CFG + PDG extraction complete.")