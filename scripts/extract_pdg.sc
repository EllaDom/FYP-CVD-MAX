val cpgFile = sys.env("CPG_FILE")
importCpg(cpgFile, "project")

import java.io.PrintWriter
import java.io.File

val split = sys.env("SPLIT")

val outDir = s"workspace/graphs/$split/pdg"
new File(outDir).mkdirs()

def clean(s: String): String =
  Option(s).getOrElse("")
    .replace("\"","'")
    .replace("\n"," ")
    .replace("\r"," ")

cpg.method
  .filter(m =>
    m.file.name.headOption.exists(name =>
      name.endsWith(".c") && !name.startsWith("<")
    )
  )
  .filter(_.cfgNode.size > 0)
  .foreach { m =>

    val fileName = m.file.name.head

    val idx =
      fileName
        .replace("\\","/")
        .split("/")
        .last
        .replace(".c","")

    // ✅ FIX: use cfgNode instead of ast
    val nodes = m.cfgNode.l.distinct.map { n =>
      s"""{
"id": ${n.id},
"label": "${clean(n.label)}",
"code": "${clean(n.code)}",
"line": ${n.lineNumber.getOrElse(-1)},
"column": ${n.columnNumber.getOrElse(-1)}
}"""
    }

    val edges =
      m.cfgNode.l.flatMap { n =>
        n.outE
          .filter(e =>
            e.label == "REACHING_DEF" ||
            e.label == "CDG"
          )
          .map { e =>
            s"""{
"source": ${e.src.id},
"target": ${e.dst.id},
"type": "PDG"
}"""
          }
      }

    val json =
s"""
{
"method": "${clean(m.name)}",
"id": ${m.id},
"nodes": [
${nodes.mkString(",")}
],
"edges": [
${edges.mkString(",")}
]
}
"""

    val file = new PrintWriter(new File(s"$outDir/$idx.json"))
    file.write(json)
    file.close()
  }

println("PDG extraction finished.")